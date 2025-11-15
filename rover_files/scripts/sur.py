import cv2 from ultralytics import YOLO from paddleocr import PaddleOCR 
import numpy as np import re import requests import threading from 
dronekit import connect, VehicleMode from pymavlink import mavutil 
import time import signal import sys import base64 from datetime import 
datetime
# ==== Config ====
BACKEND_URL = "http://192.168.104.133:5000/upload_plate" PLATE_PATTERN = 
r'^[A-Z]{2}\d{2}[A-Z]{1,2}\d{4}$' CENTER = 1500 THROTTLE_NEUTRAL = 1500 
THROTTLE_MAX = 2000 THROTTLE_MIN = 1000 THROTTLE_CH = 3 STEERING_CH = 1 
HEADLESS = True # SSH/headless mode current_throttle = THROTTLE_NEUTRAL 
current_steering = CENTER should_stop = False vehicle = None TURN_AMOUNT 
= 100 # Adjust for sharpness distance_covered = 0 slot_counter = 0 
last_distance_slot = -1 def signal_handler(sig, frame):
    global should_stop, vehicle
    print("\nCtrl+C detected. Stopping rover and cleaning up...")
    should_stop = True
    if vehicle:
        vehicle.channels.overrides = {}
        vehicle.close()
    cv2.destroyAllWindows()
    sys.exit(0) def clean_ocr_text(text):
    raw = text.upper()
    cleaned = re.sub(r'[^A-Z0-9]', '', raw)
    if not re.fullmatch(PLATE_PATTERN, cleaned):
        corrected = cleaned.replace('O', '0').replace('I', 
'1').replace('Z', '2').replace('S', '5')
        return corrected
    return cleaned def assign_slot_by_distance(distance_m):
    global slot_counter, last_distance_slot
    slot_group = int(distance_m // 2)
    if slot_group != last_distance_slot:
        slot_counter += 1
        last_distance_slot = slot_group
    group_letter = chr(65 + (slot_counter // 6) % 4) # A-D
    index = slot_counter % 6 + 1
    return f"{group_letter}{index}" def encode_image_to_base64(image):
    _, buffer = cv2.imencode('.jpg', image)
    return base64.b64encode(buffer).decode('utf-8') def 
send_to_backend(plate, slot, confidence, plate_img):
    try:
        encoded_img = encode_image_to_base64(plate_img)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "license_plate": plate,
            "slot": slot,
            "confidence": float(confidence),
            "timestamp": timestamp,
            "image": encoded_img
        }
        response = requests.post(BACKEND_URL, json=data)
        print(f"[Backend] ✅ Sent: {response.status_code} - 
{response.text}")
    except Exception as e:
        print(f"[Backend] ❌ Error sending: {e}") def get_yaw():
    attitude = vehicle.attitude
    yaw_deg = attitude.yaw * (180.0 / 3.14159)
    yaw_deg = yaw_deg if yaw_deg >= 0 else yaw_deg + 360
    return yaw_deg def normalize_angle(angle):
    while angle > 180:
        angle -= 360
    while angle < -180:
        angle += 360
    return angle def send_rc_override(throttle_pwm, steering_pwm):
    vehicle.channels.overrides = {
        THROTTLE_CH: throttle_pwm,
        STEERING_CH: steering_pwm
    }
def spin_rover(direction, duration):
    global current_throttle, current_steering
    spin_throttle = THROTTLE_NEUTRAL + 100
    if direction == 'left':
        print(f"Spinning left for {duration:.1f} seconds...")
        current_steering = max(CENTER + TURN_AMOUNT * 2, 1000)
    elif direction == 'right':
        print(f"Spinning right for {duration:.1f} seconds...")
        current_steering = min(CENTER - TURN_AMOUNT * 2, 2000)
    else:
        print("❌ Invalid spin direction.")
        return
    send_rc_override(spin_throttle, current_steering)
    start_time = time.time()
    while time.time() - start_time < duration:
        time.sleep(0.05)
    print("Stopping spin...")
    send_rc_override(THROTTLE_NEUTRAL, CENTER)
    time.sleep(0.3)
    vehicle.channels.overrides = {}
    print("✅ Spin complete.") def move_rover(direction, 
throttle_percent):
    global current_throttle
    if direction == 'f':
        current_throttle = THROTTLE_NEUTRAL + int(500 * 
(throttle_percent / 100))
    elif direction == 'b':
        current_throttle = THROTTLE_NEUTRAL - int(500 * 
(throttle_percent / 100))
    else:
        print("Invalid direction for move_rover()")
        return
    vehicle.channels.overrides = {
        THROTTLE_CH: current_throttle,
        STEERING_CH: CENTER
    }
    print(f"Moving {'forward' if direction=='f' else 'backward'} at 
{throttle_percent}% throttle") def stop_rover():
    global current_throttle
    current_throttle = THROTTLE_NEUTRAL
    vehicle.channels.overrides = {
        THROTTLE_CH: current_throttle,
        STEERING_CH: CENTER
    }
    print("Rover stopped") def detection_loop():
    global distance_covered
    yolo_model = YOLO("best.pt")
    ocr_model = PaddleOCR(use_angle_cls=True, lang='en')
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[Camera] ❌ Failed to open camera")
        return
    while not should_stop:
        ret, frame = cap.read()
        if not ret:
            print("[Camera] ❌ Failed to capture frame")
            break
        results = yolo_model.predict(source=frame, verbose=False)[0]
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            if conf < 0.8:
                continue
            plate_img = frame[y1:y2, x1:x2].copy()
            try:
                ocr_result = ocr_model.ocr(plate_img, cls=True)
                if ocr_result and len(ocr_result) > 0:
                    for line in ocr_result[0]:
                        if len(line) >= 2:
                            raw_text = line[1][0]
                            conf_score = line[1][1]
                            cleaned = clean_ocr_text(raw_text)
                            if not re.fullmatch(PLATE_PATTERN, cleaned):
                                continue
                            slot = 
assign_slot_by_distance(distance_covered)
                            print(f"[OCR] ✅ Plate: {cleaned}, Slot: 
{slot}, Conf: {conf_score:.2f}")
                            send_to_backend(cleaned, slot, conf_score, 
plate_img)
            except Exception as e:
                print(f"[OCR] ❌ Error: {e}")
    cap.release() def main():
    global vehicle, should_stop
    signal.signal(signal.SIGINT, signal_handler)
    try:
        vehicle = connect('/dev/ttyUSB0', baud=57600, wait_ready=False)
        print("Connected to vehicle")
    except Exception as e:
        print(f"Failed to connect to vehicle: {e}")
        return
    detection_thread = threading.Thread(target=detection_loop)
    detection_thread.daemon = True
    detection_thread.start()
    try:
        while not should_stop:
            cmd = input("Enter command (f=forward, b=backward, s=stop, 
l=left, r=right, u=uturn): ").strip().lower()
            if cmd == 's':
                stop_rover()
            elif cmd in ['f', 'b']:
                try:
                    throttle = int(input("Throttle % (0–100): "))
                    if not (0 <= throttle <= 100):
                        print("Throttle must be between 0 and 100")
                        continue
                except ValueError:
                    print("Invalid throttle input")
                    continue
                move_rover(cmd, throttle)
            elif cmd == 'l':
                spin_rover('left', 1)
            elif cmd == 'r':
                spin_rover('right', 1)
            elif cmd == 'u':
                spin_rover('right', 2)
            else:
                print("❌ Unknown command.")
    finally:
        should_stop = True
        stop_rover()
        if vehicle:
            vehicle.channels.overrides = {}
            vehicle.close()
        print("Exited cleanly") if _name_ == "_main_":
    main()
