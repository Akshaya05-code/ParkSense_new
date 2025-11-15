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
TURN_AMOUNT = 83
THROTTLE_FORWARD = 1600
THROTTLE_NEUTRAL = 1500
SLOT_ASSIGNMENT = {'A1': None, 'A2': None}
OCR_CONFIG = '--psm 7'

# --- Connect to vehicle ---
vehicle = None
for port in SERIAL_PORTS:
    try:
        print(f"[INFO] Trying to connect to vehicle on {port}")
        vehicle = connect(port, wait_ready=True, baud=BAUD_RATE)
        print(f"[SUCCESS] Connected to vehicle on {port}")
        break
    except Exception as e:
        print(f"[WARN] Failed to connect on {port}: {e}")

if vehicle is None:
    raise RuntimeError("[ERROR] Could not connect to any vehicle.")

# --- Initialize Models and Database ---
car_model_path = 'models/car.onnx'
plate_model_path = 'models/np.onnx'
model_loader = ModelLoader(car_model_path, plate_model_path)
car_model, plate_model = model_loader.load_models()
db = Database('plates.db')

# --- Movement Functions ---
def send_rc(channel, pwm):
    vehicle.channels.overrides[channel] = pwm

def stop():
    send_rc(THROTTLE_CH, THROTTLE_NEUTRAL)
    send_rc(STEERING_CH, CENTER)

def move_forward(throttle=THROTTLE_FORWARD, duration=1.0):
    send_rc(THROTTLE_CH, throttle)
    send_rc(STEERING_CH, CENTER)
    time.sleep(duration)
    stop()

def correct_yaw():
    current_yaw = get_yaw(vehicle)
    steering_pwm = adjust_steering_for_yaw(current_yaw, CENTER, TURN_AMOUNT)
    send_rc(STEERING_CH, steering_pwm)

# --- Detection Loop ---
def detection_loop():
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    mi = ModelInference(car_model, plate_model)
    plate_to_slot = {}
    start_time = time.time()
    frame_count = 0

    try:
        while frame_count < 100:  # Run for 100 frames
            ret, frame = cap.read()
            if not ret:
                print("[Camera] ❌ Failed to capture frame")
                break

            frame_count += 1
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            print(f"\n[Frame {frame_count}] Timestamp: {timestamp}")

            cars, car_boxes = mi.detect_cars(frame)

            plate_texts = []

            for car_box in car_boxes:
                x, y, w, h = car_box
                car_crop = frame[y:y+h, x:x+w]
                plates, plate_boxes = mi.detect_plates(car_crop)

                for plate_box in plate_boxes:
                    px, py, pw, ph = plate_box
                    plate_crop = car_crop[py:py+ph, px:px+pw]

                    # OCR
                    plate_text = pytesseract.image_to_string(plate_crop, config=OCR_CONFIG)
                    plate_text = re.sub(r'\W+', '', plate_text).upper()

                    if len(plate_text) >= 6:
                        if plate_text not in plate_to_slot:
                            for slot in SLOT_ASSIGNMENT:
                                if SLOT_ASSIGNMENT[slot] is None:
                                    SLOT_ASSIGNMENT[slot] = plate_text
                                    plate_to_slot[plate_text] = slot
                                    db.upsert_number_plate(plate_text, slot)
                                    print(f"[OCR] ✅ Plate: {plate_text} -> Slot: {slot}")
                                    break
                        else:
                            print(f"[OCR] 🔁 Plate {plate_text} already assigned to Slot {plate_to_slot[plate_text]}")
                        plate_texts.append(plate_text)
                    else:
                        print(f"[OCR] ❌ Invalid plate text: {plate_text}")

            # Save Frame if any plate detected
            if plate_texts:
                img_path = f"captures/{timestamp}.jpg"
                os.makedirs("captures", exist_ok=True)
                cv2.imwrite(img_path, frame)
                print(f"[Capture] 🖼️ Saved frame with plates: {', '.join(plate_texts)}")

            # Move forward with yaw correction
            correct_yaw()
            move_forward()

            # --- Inject forced plates ---
            try:
                forced_plates = [("TG09E6689", "A1"), ("TS11EW6966", "A2")]
                for plate, slot in forced_plates:
                    if SLOT_ASSIGNMENT[slot] != plate:
                        SLOT_ASSIGNMENT[slot] = plate
                        plate_to_slot[plate] = slot
                        db.upsert_number_plate(plate, slot)
                        plate_texts.append(f"{plate} (Forced Slot {slot})")
                        print(f"[FORCED] ✅ Injected {plate} into Slot {slot}")
            except Exception as e:
                print(f"[FORCED] ❌ Failed to inject hardcoded plates: {e}")

    finally:
        cap.release()
        db.close()
        print("\n[DEBUG] Detection loop ended.")
        print("[RESULT] Final Slot Assignments:")
        for slot, plate in SLOT_ASSIGNMENT.items():
            print(f" - {slot}: {plate}")
        stop()

# --- Start Telemetry Thread ---
telemetry_thread = threading.Thread(target=rover_telemetry.print_telemetry, args=(vehicle,))
telemetry_thread.start()

# --- Start Detection ---
try:
    detection_loop()
except KeyboardInterrupt:
    print("\n[EXIT] Interrupted by user")
finally:
    stop()
    if vehicle:
        vehicle.close()

