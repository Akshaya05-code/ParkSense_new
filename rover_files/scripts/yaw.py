import math

# Constants from rover.py
CENTER = 1500
TURN_AMOUNT = 90
MIN_STEERING = 1000
MAX_STEERING = 2000

def get_yaw(vehicle):
    """
    Retrieves the current yaw from the vehicle in degrees.
    Returns None if yaw is unavailable.
    """
    try:
        return math.degrees(vehicle.attitude.yaw)
    except AttributeError:
        print("Warning: Could not retrieve attitude information.")
        return None

def adjust_steering_for_yaw(vehicle, initial_yaw, drift_threshold, yaw_buffer=None):
    """
    Calculates steering to correct yaw deviation based on threshold.
    Returns steering value (PWM) using the exact logic from rover.py.
    Note: yaw_buffer is included for compatibility but not used.
    """
    yaw = get_yaw(vehicle)
    if yaw is None or initial_yaw is None:
        return CENTER

    yaw_deviation = yaw - initial_yaw
    # Normalize the angle difference to be within -180 to 180 degrees
    if yaw_deviation > 180:
        yaw_deviation -= 360
    elif yaw_deviation < -180:
        yaw_deviation += 360

    if yaw_deviation > drift_threshold:  # Drifting right, correct left
        steering = max(CENTER - TURN_AMOUNT, MIN_STEERING)
    elif yaw_deviation < -drift_threshold:  # Drifting left, correct right
        steering = min(CENTER + TURN_AMOUNT, MAX_STEERING)
    else:
        steering = CENTER

    return int(steering)
