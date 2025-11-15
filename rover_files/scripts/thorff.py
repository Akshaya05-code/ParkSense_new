import time
import os
import cv2
import pytesseract
from datetime import datetime
from dronekit import connect, VehicleMode
from model_loader import ModelLoader
from model_inference import ModelInference
from database import Database
from yaw import get_yaw, adjust_steering_for_yaw
import math
import re
import rover_telemetry
import threading
import queue

# --- Configuration ---
SERIAL_PORTS = ['/dev/ttyUSB0', 'COM3']
BAUD_RATE = 57600
THROTTLE_CH = 3
STEERING_CH = 1
CENTER = 1500
THROTTLE_NEUTRAL = 1500
THROTTLE_MAX = 2000
DURATION = 40  # seconds
honey = 0.2
MAX_SPEED_MPS = 1.0
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
CAR_MODEL = '../models/car.onnx'
NP_MODEL = '../models//np.onnx'
SLOT_SIZE = 1.6  # meters per slot

def correct_by_position(ocr_str):
    ocr_str = re.sub(r'[^A-Za-z0-9]', '', ocr_str).upper()
    digit_to_alpha = {'0': 'O', '1': 'I', '2': 'Z', '4': 'A', '5': 'S', '8': 'B', '6': 'G'}
    alpha_to_digit = {'O': '0', 'I': '1', 'Z': '2', 'S': '5', 'B': '8', 'G': '6', 'Q': '0', 'L': '1', 'E': '6', 'J': '3', ']': '3'}
    letters = []
    digits = []
    i = 0
    while len(letters) < 2 and i < len(ocr_str):
        ch = ocr_str[i]
        if ch.isalpha():
            letters.append(ch)
        elif ch in digit_to_alpha:
            letters.append(digit_to_alpha[ch])
        i += 1
    while len(digits) < 2 and i < len(ocr_str):
        ch = ocr_str[i]
        if ch.isdigit():
            digits.append(ch)
        elif ch in alpha_to_digit:
            digits.append(alpha_to_digit[ch])
        i += 1
    if len(ocr_str) == 10:
        while len(letters) < 4 and i < len(ocr_str):
            ch = ocr_str[i]
            if ch.isalpha():
                letters.append(ch)
            elif ch in digit_to_alpha:
                letters.append(digit_to_alpha[ch])
            i += 1
    elif len(ocr_str) == 9:
        while len(letters) < 3 and i < len(ocr_str):
            ch = ocr_str[i]
            if ch.isalpha():
                letters.append(ch)
            elif ch in digit_to_alpha:
                letters.append(digit_to_alpha[ch])
            i += 1
    while len(digits) < 6 and i < len(ocr_str):
        ch = ocr_str[i]
        if ch.isdigit():
            digits.append(ch)
        elif ch in alpha_to_digit:
            digits.append(alpha_to_digit[ch])
        i += 1
    if len(letters) < 3 or len(digits) < 6:
        return "Could not parse correctly"
    part1 = ''.join(letters[:2])
    part2 = ''.join(digits[:2])
    part3 = ''.join(letters[2:4])
    part4 = ''.join(digits[2:6])
    return part1 + part2 + part3 + part4

def send_rc(vehicle, throttle, steering):
    vehicle.channels.overrides = {THROTTLE_CH: throttle, STEERING_CH: steering}
    print(f"[DEBUG] RC override -> Throttle: {throttle}, Steering: {steering}")

def connect_vehicle():
    for port in SERIAL_PORTS:
        try:
            v = connect(port, baud=BAUD_RATE, wait_ready=False)
            print(f"[DEBUG] Connected to vehicle on {port}")
            return v
        except Exception as e:
            print(f"[DEBUG] Failed to connect on {port}: {e}")
    raise RuntimeError("Unable to connect to any Pixhawk port.")

def arm_and_manual(vehicle):
    print("[DEBUG] Performing pre-arm checks...")
    timeout = time.time() + 10
    while not vehicle.is_armable and time.time() < timeout:
        fix = getattr(vehicle.gps_0, 'fix_type', 'N/A')
        sats = getattr(vehicle.gps_0, 'satellites_visible', 'N/A')
        volt = getattr(vehicle.battery, 'voltage', 'N/A')
        print(f"  [DEBUG] Waiting: GPS fix {fix}, sats {sats}, battery {volt}V")
        time.sleep(1)
    if not vehicle.is_armable:
        print("[DEBUG] Warning: Vehicle not armable. Proceeding without arming.")
    else:
        vehicle.armed = True
        while not vehicle.armed and time.time() < timeout:
            print("  [DEBUG] Waiting for arming...")
            time.sleep(1)
        vehicle.mode = VehicleMode('MANUAL')
        mtimeout = time.time() + 10
        while vehicle.mode.name != 'MANUAL' and time.time() < mtimeout:
            print(f"  [DEBUG] Switching mode: current {vehicle.mode.name}")
            vehicle.mode = VehicleMode('MANUAL')
            time.sleep(1)
        print(f"[DEBUG] Armed: {vehicle.armed}, Mode: {vehicle.mode.name}")

def preprocess_plate(plate_img):
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

def get_slot_number(distance):
    slot_num = math.floor(distance / SLOT_SIZE) + 1
    return f"A{slot_num}"

def yaw_correction_thread(vehicle, initial_yaw, drift_threshold, steering_queue, stop_event):
    """Thread to handle yaw correction and update steering value."""
    while not stop_event.is_set():
        try:
            if initial_yaw is not None and drift_threshold is not None:
                steering = adjust_steering_for_yaw(vehicle, initial_yaw, drift_threshold)
                steering_queue.put(steering)
                print(f"[DEBUG] Yaw thread: Updated steering to {steering}")
            else:
                steering_queue.put(CENTER)
                print("[DEBUG] Yaw thread: No yaw data, using center steering")
            time.sleep(0.1)  # Adjust yaw check frequency
        except Exception as e:
            print(f"[ERROR] Yaw correction error: {e}")
            steering_queue.put(CENTER)
            time.sleep(0.1)

def np_detection_thread(cap, inference, db, output_dir, speed_factor, stop_event, result_queue):
    """Thread to handle frame capture, NP detection, and OCR processing."""
    num_frames = 0
    car_count = 0
    plate_count = 0
    plate_texts = []
    plate_image_paths = []
    cumulative_distance = 0.0
    last_time = time.time()

    while not stop_event.is_set():
        try:
            ret, frame = cap.read()
            if not ret:
                print("[DEBUG] NP thread: Frame read failed; skipping.")
                continue

            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time
            distance_increment = speed_factor * MAX_SPEED_MPS * dt
            cumulative_distance += distance_increment
            slot = get_slot_number(cumulative_distance)

            num_frames += 1
            ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
            print(f"\n[DEBUG] NP thread: Frame #{num_frames} @ {ts} | +{distance_increment:.3f}m -> Slot {slot}")

            raw_fp = os.path.join(output_dir, f"frame_{ts}.jpg")
            cv2.imwrite(raw_fp, frame)
            print(f"[DEBUG] NP thread: Saved raw frame: {raw_fp}")

            vis_fp = os.path.join(output_dir, f"vis_{ts}.jpg")
            cars, cscores, cids, plates, pscores, pids = inference.infer(raw_fp, vis_fp)
            print(f"[DEBUG] NP thread: Detected {len(cars)} cars, {len(plates)} plates")

            # Process car crops
            try:
                if len(cars) > 0:
                    height, width = frame.shape[:2]
                    for i, (x1, y1, x2, y2) in enumerate(cars):
                        print(f"[DEBUG] NP thread: Car {i} bbox: ({x1:.1f},{y1:.1f})→({x2:.1f},{y2:.1f})")
                        x1 = max(0, int(x1))
                        y1 = max(0, int(y1))
                        x2 = min(width, int(x2))
                        y2 = min(height, int(y2))
                        if x2 > x1 and y2 > y1:
                            crop = frame[y1:y2, x1:x2]
                            if not crop.size == 0:
                                cf = os.path.join(output_dir, f"car_{ts}_{i}.jpg")
                                cv2.imwrite(cf, crop)
                                print(f"[DEBUG] NP thread: Saved car crop: {cf}")
                                car_count += 1
                            else:
                                print(f"[DEBUG] NP thread: Skipped car {i} crop: empty image")
                        else:
                            print(f"[DEBUG] NP thread: Skipped car {i} crop: invalid bbox")
            except Exception as car_err:
                print(f"[ERROR] NP thread: Car crop processing error: {car_err}")

            # Process plate crops + OCR
            try:
                if len(plates) > 0:
                    height, width = frame.shape[:2]
                    for j, (x1, y1, x2, y2) in enumerate(plates):
                        print(f"[DEBUG] NP thread: Plate {j} bbox: ({x1:.1f},{y1:.1f})→({x2:.1f},{y2:.1f})")
                        x1 = max(0, int(x1))
                        y1 = max(0, int(y1))
                        x2 = min(width, int(x2))
                        y2 = min(height, int(y2))
                        if x2 > x1 and y2 > y1:
                            crop = frame[y1:y2, x1:x2]
                            if not crop.size == 0:
                                pf = os.path.join(output_dir, f"plate_{ts}_{j}.jpg")
                                cv2.imwrite(pf, crop)
                                plate_image_paths.append(pf)
                                plate_count += 1
                                print(f"[DEBUG] NP thread: Saved plate crop: {pf}")

                                processed = preprocess_plate(crop)
                                text = pytesseract.image_to_string(processed, config='--psm 7').strip()
                                print(f"[DEBUG] NP thread: Raw OCR output: '{text}'")
                                if text:
                                    corrected_text = correct_by_position(text)
                                    print(f"[DEBUG] NP thread: Corrected OCR output: '{corrected_text}'")
                                    if corrected_text != "Could not parse correctly":
                                        plate_texts.append(f"{corrected_text} (Pending, Slot {slot})")
                                        if db:
                                            db.log_car_entry(corrected_text, slot)
                                            db.upsert_number_plate(corrected_text, slot)
                                    else:
                                        print("[DEBUG] NP thread: OCR correction failed: Could not parse correctly")
                                        plate_texts.append(f"{text} (Parse Failed, Slot {slot})")
                                else:
                                    print("[DEBUG] NP thread: No text extracted.")
                                    plate_texts.append(f"No text extracted (Slot {slot})")
                            else:
                                print(f"[DEBUG] NP thread: Skipped plate {j} crop: empty image")
                        else:
                            print(f"[DEBUG] NP thread: Skipped plate {j} crop: invalid bbox")
            except Exception as plate_err:
                print(f"[ERROR] NP thread: Plate processing error: {plate_err}")

            # Store results in queue for main thread
            result_queue.put({
                'num_frames': num_frames,
                'car_count': car_count,
                'plate_count': plate_count,
                'plate_texts': plate_texts.copy(),
                'plate_image_paths': plate_image_paths.copy(),
                'cumulative_distance': cumulative_distance
            })

            time.sleep(0.05)  # Control frame processing rate
        except Exception as frame_err:
            print(f"[ERROR] NP thread: Frame #{num_frames} processing error: {frame_err}")

def main():
    cap = None
    vehicle = None
    db = None
    start_time = None
    stop_event = threading.Event()
    steering_queue = queue.Queue()
    result_queue = queue.Queue()

    try:
        db = Database()
        vehicle = connect_vehicle()
        arm_and_manual(vehicle)
        initial_yaw = get_yaw(vehicle)
        if initial_yaw is None:
            print("Warning: Initial yaw unavailable. Yaw correction will not be applied.")
            drift_threshold = None
        else:
            drift_threshold = 2

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            print("[DEBUG] Cannot open webcam at index 0. Trying index 1...")
            cap = cv2.VideoCapture(1)
            if not cap.isOpened():
                print("[ERROR] Cannot open webcam at index 1. Ensure a webcam is connected.")
                return

        print("[DEBUG] Webcam connected. Loading models...")
        loader = ModelLoader(CAR_MODEL, NP_MODEL)
        inference = ModelInference(loader)

        throttle_val = int(THROTTLE_NEUTRAL + (THROTTLE_MAX - THROTTLE_NEUTRAL) * honey)
        speed_factor = (throttle_val - THROTTLE_NEUTRAL) / float(THROTTLE_MAX - THROTTLE_NEUTRAL)
        print(f"[DEBUG] Speed factor set to {speed_factor:.2f}")

        # Start threads
        yaw_thread = threading.Thread(
            target=yaw_correction_thread,
            args=(vehicle, initial_yaw, drift_threshold, steering_queue, stop_event)
        )
        np_thread = threading.Thread(
            target=np_detection_thread,
            args=(cap, inference, db, OUTPUT_DIR, speed_factor, stop_event, result_queue)
        )
        yaw_thread.start()
        np_thread.start()
        print("[DEBUG] Started yaw and NP detection threads.")

        start_time = time.time()
        print("[DEBUG] Entering main control loop...")

        while time.time() - start_time < DURATION:
            try:
                # Get steering value from yaw thread
                steering = CENTER
                try:
                    if not steering_queue.empty():
                        steering = steering_queue.get_nowait()
                except queue.Empty:
                    pass

                send_rc(vehicle, throttle_val, steering)
                time.sleep(0.05)
            except Exception as e:
                print(f"[ERROR] Main loop error: {e}")

        print("[DEBUG] Movement duration ended; stopping threads...")
        stop_event.set()

        # Stop vehicle
        for _ in range(5):
            send_rc(vehicle, THROTTLE_NEUTRAL, CENTER)
            time.sleep(0.2)
        vehicle.channels.overrides = {}

        # Wait for threads to finish
        yaw_thread.join()
        np_thread.join()
        print("[DEBUG] Threads stopped.")

        # Retrieve final results from NP thread
        final_results = {}
        while not result_queue.empty():
            final_results = result_queue.get()

        if final_results:
            num_frames = final_results.get('num_frames', 0)
            car_count = final_results.get('car_count', 0)
            plate_count = final_results.get('plate_count', 0)
            plate_texts = final_results.get('plate_texts', [])
            plate_image_paths = final_results.get('plate_image_paths', [])
            cumulative_distance = final_results.get('cumulative_distance', 0.0)
        else:
            num_frames = 0
            car_count = 0
            plate_count = 0
            plate_texts = []
            plate_image_paths = []
            cumulative_distance = 0.0

    except Exception as e:
        print(f"[ERROR] Setup/main loop failure: {e}")

    finally:
        # Log telemetry data once after main loop
        if vehicle and db:
            try:
                print("[DEBUG] Logging final telemetry data...")
                rover_telemetry.log_telemetry_once(vehicle, db)
            except Exception as telemetry_err:
                print(f"[ERROR] Telemetry logging error: {telemetry_err}")

        # Clean up resources
        stop_event.set()
        if cap:
            cap.release()
        if vehicle:
            try:
                vehicle.close()
            except:
                pass
        if db:
            db.close()
        print("[DEBUG] Resources cleaned up.")

        if start_time is not None:
            elapsed = time.time() - start_time
            fps = num_frames / elapsed if elapsed > 0 else 0.0
            final_slot = get_slot_number(cumulative_distance)
            print("\n=== Final Detection Summary ===")
            print(f"Frames processed:       {num_frames}")
            print(f"Overall FPS:           {fps:.2f}")
            print(f"Total cars detected:   {car_count}")
            print(f"Total plates detected: {plate_count}")
            print(f"Extracted plate texts: {plate_texts}")
            print(f"Total distance:        {cumulative_distance:.3f} m (Slot {final_slot})")
            print(f"Saved plate images ({len(plate_image_paths)}):")
            for p in plate_image_paths:
                print(f"  • {p}")
        else:
            print("[DEBUG] Main loop did not start due to earlier errors.")

if __name__ == '__main__':
    main()
