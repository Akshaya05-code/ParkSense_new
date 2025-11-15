import time
import os
import cv2
import pytesseract
import numpy as np
from datetime import datetime
from dronekit import connect, VehicleMode
from model_loader import ModelLoader
from model_inference import ModelInference
from database import Database
from yaw import get_yaw, adjust_steering_for_yaw
import math
import re
import threading
import rover_telemetry

# --- Configuration ---
SERIAL_PORTS = ['/dev/ttyUSB0', 'COM3']
BAUD_RATE = 57600
THROTTLE_CH = 3
STEERING_CH = 1
CENTER = 1500
THROTTLE_NEUTRAL = 1500
THROTTLE_MAX = 2000
THROTTLE_MIN = 1000
TURN_AMOUNT = 200  # For yaw correction
DURATION = 45  # seconds (20s forward + spin + 20s forward + spin + buffer)
MAX_SPEED_MPS = 1.0
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
CAR_MODEL = '../models/car.onnx'
NP_MODEL = '../models//np.onnx'
PLATE_PATTERN = r'^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$'

# Global variables
current_throttle = THROTTLE_NEUTRAL
current_steering = CENTER
should_stop = False
distance_covered = 0.0
slot_counter = 0
last_distance_slot = -1
plate_to_slot = {}  # Plate-to-slot mappings

def clean_ocr_text(text):
    raw = text.upper()
    cleaned = re.sub(r'[^A-Z0-9]', '', raw)
    if not re.fullmatch(PLATE_PATTERN, cleaned):
        corrected = cleaned.replace('O', '0').replace('I', '1').replace('Z', '2').replace('S', '5')
        return corrected if re.fullmatch(PLATE_PATTERN, corrected) else None
    return cleaned

def assign_slot_by_distance(distance_m):
    global slot_counter, last_distance_slot
    slot_group = int(distance_m // 2)
    if slot_group != last_distance_slot:
        slot_counter += 1
        last_distance_slot = slot_group
    group_letter = chr(65 + (slot_counter // 6) % 4)  # A-D
    index = slot_counter % 6 + 1
    return f"{group_letter}{index}"

def preprocess_plate(plate_img):
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

def send_rc_override(vehicle, throttle_pwm, steering_pwm):
    vehicle.channels.overrides = {
        THROTTLE_CH: throttle_pwm,
        STEERING_CH: steering_pwm
    }
    print(f"[DEBUG] Sent: Throttle: {throttle_pwm}, Steering: {steering_pwm}")

def spin_rover(vehicle, direction, duration):
    global current_throttle, current_steering
    spin_throttle = THROTTLE_NEUTRAL + 10
    if direction == 'left':
        print(f"Spinning left for {duration:.1f} seconds...")
        current_steering = max(CENTER + TURN_AMOUNT * 2, 1000)
    elif direction == 'right':
        print(f"Spinning right for {duration:.1f} seconds...")
        current_steering = min(CENTER - TURN_AMOUNT * 2, 2000)
    else:
        print("❌ Invalid direction.")
        return
    send_rc_override(vehicle, spin_throttle, current_steering)
    start_time = time.time()
    while time.time() - start_time < duration and not should_stop:
        time.sleep(0.05)
    print("Stopping spin...")
    stop_rover(vehicle)
    print("✅ Spin complete.")

def move_rover(vehicle, direction, throttle_percent):
    global current_throttle
    if direction == 'f':
        current_throttle = THROTTLE_NEUTRAL + int(500 * (throttle_percent / 100))
    elif direction == 'b':
        current_throttle = THROTTLE_NEUTRAL - int(500 * (throttle_percent / 100))
    else:
        print("Invalid direction for move_rover()")
        return
    send_rc_override(vehicle, current_throttle, CENTER)
    print(f"Moving {'forward' if direction=='f' else 'backward'} at {throttle_percent}% throttle")

def stop_rover(vehicle):
    global current_throttle, current_steering, should_stop
    current_throttle = THROTTLE_NEUTRAL
    current_steering = CENTER
    for _ in range(3):  # Send multiple times for reliability
        send_rc_override(vehicle, THROTTLE_NEUTRAL, CENTER)
        time.sleep(0.1)
    vehicle.channels.overrides = {}
    time.sleep(0.3)  # Increased delay for Pixhawk
    print("Rover stopped")

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

def detection_loop():
    global distance_covered, should_stop, plate_to_slot
    try:
        loader = ModelLoader(CAR_MODEL, NP_MODEL)
        inference = ModelInference(loader, conf_threshold=0.6, iou_threshold=0.45)
    except FileNotFoundError as e:
        print(f"[ERROR] Model file not found: {e}")
        return
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[Camera] ❌ Failed to open camera at index 0. Trying index 1...")
        cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            print("[Camera] ❌ Failed to open camera at index 1.")
            return
    num_frames = 0
    car_count = 0
    plate_count = 0
    plate_texts = []
    plate_image_paths = []
    last_time = time.time()
    db = Database()
    while not should_stop:
        ret, frame = cap.read()
        if not ret:
            print("[Camera] ❌ Failed to capture frame")
            break
        num_frames += 1
        ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        current_time = time.time()
        dt = current_time - last_time
        last_time = current_time
        speed_factor = (current_throttle - THROTTLE_NEUTRAL) / 500.0 if current_throttle != THROTTLE_NEUTRAL else 0
        distance_increment = speed_factor * MAX_SPEED_MPS * dt
        distance_covered += distance_increment
        slot = assign_slot_by_distance(distance_covered)
        print(f"\n[DEBUG] Frame #{num_frames} @ {ts} | +{distance_increment:.3f}m -> Slot {slot}")
        try:
            cars, cscores, cids, plates, pscores, pids = inference.infer_frame(frame)
            print(f"[DEBUG] Detected {len(cars)} cars, {len(plates)} plates")
            height, width = frame.shape[:2]
            for i, (x1, y1, x2, y2) in enumerate(cars):
                x1 = max(0, int(x1))
                y1 = max(0, int(y1))
                x2 = min(width, int(x2))
                y2 = min(height, int(y2))
                if x2 > x1 and y2 > y1:
                    crop = frame[y1:y2, x1:x2]
                    if crop.size != 0:
                        cf = os.path.join(OUTPUT_DIR, f"car_{ts}_{i}.jpg")
                        cv2.imwrite(cf, crop)
                        print(f"[DEBUG] Saved car crop: {cf}")
                        car_count += 1
            for j, (x1, y1, x2, y2) in enumerate(plates):
                x1 = max(0, int(x1))
                y1 = max(0, int(y1))
                x2 = min(width, int(x2))
                y2 = min(height, int(y2))
                if x2 > x1 and y2 > y1:
                    crop = frame[y1:y2, x1:x2]
                    if crop.size != 0:
                        pf = os.path.join(OUTPUT_DIR, f"plate_{ts}_{j}.jpg")
                        cv2.imwrite(pf, crop)
                        plate_image_paths.append(pf)
                        plate_count += 1
                        print(f"[DEBUG] Saved plate crop: {pf}")
                        processed = preprocess_plate(crop)
                        text = pytesseract.image_to_string(processed, config='--psm 7').strip()
                        print(f"[DEBUG] Raw OCR output: '{text}'")
                        if text:
                            cleaned = clean_ocr_text(text)
                            if cleaned:
                                try:
                                    db.upsert_number_plate(cleaned, slot)
                                    print(f"[DB] ✅ Upserted plate: {cleaned}, Slot: {slot}")
                                except Exception as e:
                                    print(f"[DB] ❌ Error upserting plate: {e}")
                                plate_texts.append(f"{cleaned} (Slot {slot}, Conf {pscores[j]:.2f})")
                                plate_to_slot[cleaned] = slot
                            else:
                                print("[DEBUG] OCR correction failed: Invalid plate format")
                                plate_texts.append(f"{text} (Parse Failed, Slot {slot})")
                        else:
                            print("[DEBUG] No text extracted.")
                            plate_texts.append(f"No text extracted (Slot {slot})")
        except Exception as e:
            print(f"[ERROR] Detection error: {e}")
        time.sleep(0.01)  # Prevent CPU overload
    cap.release()
    db.close()
    print("\n[DEBUG] Detection loop ended.")
    print(f"[DEBUG] Frames processed: {num_frames}")
    print(f"[DEBUG] Total cars detected: {car_count}")
    print(f"[DEBUG] Total plates detected: {plate_count}")
    print(f"[DEBUG] Extracted plate texts: {plate_texts}")
    print(f"[DEBUG] Saved plate images ({len(plate_image_paths)}):")
    for p in plate_image_paths:
        print(f"  • {p}")

def main():
    global should_stop, distance_covered
    vehicle = None
    db = None
    start_time = None
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

        print("[DEBUG] Starting detection thread...")
        detection_thread = threading.Thread(target=detection_loop)
        detection_thread.daemon = True
        detection_thread.start()

        start_time = time.time()
        print("[DEBUG] Starting automated movement sequence...")

        # Step 1: Move forward for 20 seconds
        if not should_stop:
            print("[AUTO] Moving forward for 20 seconds...")
            move_rover(vehicle, 'f', 30)
            move_start = time.time()
            while time.time() - move_start < 20 and not should_stop:
                if drift_threshold is not None:
                    steering = adjust_steering_for_yaw(vehicle, initial_yaw, drift_threshold)
                    send_rc_override(vehicle, current_throttle, steering)
                time.sleep(0.05)
            stop_rover(vehicle)

        # Step 2: Spin 180 degrees to reverse direction
        if not should_stop:
            spin_rover(vehicle, 'right', 0.9)  # Adjust duration if needed

        # Step 3: Move forward for 20 seconds to return
        if not should_stop:
            print("[AUTO] Moving forward for 20 seconds to return...")
            move_rover(vehicle, 'f', 30)
            move_start = time.time()
            while time.time() - move_start < 20 and not should_stop:
                if drift_threshold is not None:
                    steering = adjust_steering_for_yaw(vehicle, initial_yaw, drift_threshold)
                    send_rc_override(vehicle, current_throttle, steering)
                time.sleep(0.05)
            stop_rover(vehicle)

        # Step 4: Spin 180 degrees to initial orientation
        if not should_stop:
            spin_rover(vehicle, 'right', 0.9)  # Adjust duration if needed

        print("\n[DEBUG] Automated sequence complete; stopping rover...")
        stop_rover(vehicle)

    except Exception as e:
        print(f"[ERROR] Setup/sequence failure: {e}")

    finally:
        should_stop = True
        if 'detection_thread' in locals() and detection_thread.is_alive():
            detection_thread.join(timeout=2.0)
        if vehicle and db:
            try:
                print("[DEBUG] Logging final telemetry data...")
                rover_telemetry.log_telemetry_once(vehicle, db)
            except Exception as telemetry_err:
                print(f"[ERROR] Telemetry logging error: {telemetry_err}")
        if vehicle:
            try:
                vehicle.close()
            except:
                pass
        if db:
            db.close()
        print("[DEBUG] Resources cleaned up.")
        final_slot = assign_slot_by_distance(distance_covered)
        print(f"\n=== Final Detection Summary ===")
        print(f"Total distance:        {distance_covered:.3f} m (Slot {final_slot})")
        print("Car to Slot Mapping:")
        if plate_to_slot:
            for plate, slot in plate_to_slot.items():
                print(f"  • Car with plate {plate} in Slot {slot}")
        else:
            print("  • No cars detected.")

if __name__ == '__main__':
    main()
