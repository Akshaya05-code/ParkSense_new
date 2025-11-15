import time
from dronekit import connect, VehicleMode
from yaw import get_yaw, adjust_steering_for_yaw

# Configuration
SERIAL_PORTS = ['/dev/ttyUSB0', 'COM3']
BAUD_RATE = 57600
THROTTLE_CH = 3  # Forward/Backward
STEERING_CH = 1  # Left/Right steering
CENTER = 1500
THROTTLE_NEUTRAL = 1500
THROTTLE_MAX = 2000
DURATION = 20  # seconds
THROTTLE_PERCENT = 40  # 30% throttle
DRIFT_THRESHOLD = 2  # Degrees of yaw deviation before correction

def connect_vehicle():
    for port in SERIAL_PORTS:
        try:
            vehicle = connect(port, baud=BAUD_RATE, wait_ready=False)
            print(f"[DEBUG] Connected to vehicle on {port}")
            return vehicle
        except Exception as e:
            print(f"[DEBUG] Failed to connect on {port}: {e}")
    raise RuntimeError("Unable to connect to any Pixhawk port.")

def arm_and_manual(vehicle):
    print("[DEBUG] Performing pre-arm checks...")
    timeout = time.time() + 10
    while not vehicle.is_armable and time.time() < timeout:
        print("  [DEBUG] Waiting for vehicle to become armable...")
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

def send_rc(vehicle, throttle, steering):
    vehicle.channels.overrides = {THROTTLE_CH: throttle, STEERING_CH: steering}
    print(f"[DEBUG] RC override -> Throttle: {throttle}, Steering: {steering}")

def main():
    vehicle = None
    try:
        vehicle = connect_vehicle()
        arm_and_manual(vehicle)
        initial_yaw = get_yaw(vehicle)
        if initial_yaw is None:
            print("Warning: Initial yaw unavailable. Yaw correction will not be applied.")
            return

        print(f"[DEBUG] Initial yaw: {initial_yaw:.1f} degrees")

        # Calculate throttle value for 30% forward
        throttle_val = int(THROTTLE_NEUTRAL + (THROTTLE_MAX - THROTTLE_NEUTRAL) * (THROTTLE_PERCENT / 100.0))
        print(f"[DEBUG] Throttle set to {throttle_val} for 30% forward")

        start_time = time.time()
        while time.time() - start_time < DURATION:
            steering = adjust_steering_for_yaw(vehicle, initial_yaw, DRIFT_THRESHOLD)
            send_rc(vehicle, throttle_val, steering)
            current_yaw = get_yaw(vehicle)
            if current_yaw is not None:
                print(f"[DEBUG] Time: {time.time() - start_time:.1f}s, Current yaw: {current_yaw:.1f} degrees, Steering: {steering}")
            else:
                print(f"[DEBUG] Time: {time.time() - start_time:.1f}s, Yaw unavailable, Steering: {steering}")
            time.sleep(0.1)

        print("\n[DEBUG] Movement duration ended; stopping rover...")
        for _ in range(5):
            send_rc(vehicle, THROTTLE_NEUTRAL, CENTER)
            time.sleep(0.2)
        vehicle.channels.overrides = {}

    except Exception as e:
        print(f"[ERROR] Test failure: {e}")

    finally:
        if vehicle:
            try:
                vehicle.close()
            except:
                pass
        print("[DEBUG] Resources cleaned up.")

if __name__ == '__main__':
    main()
