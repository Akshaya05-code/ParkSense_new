from yaw import RoverController
import time

def main():
    rover = RoverController(connection_string='/dev/ttyUSB0', baud=57600)
    rover.connect_vehicle()

    # Uncomment if you want to arm and takeoff (for copters)
    # rover.arm_and_takeoff(2)

    # Move forward 50% throttle for 5 seconds with yaw correction
    rover.move_rover('forward', throttle_percent=35, duration=20)

    # Spin right for 3 seconds
    rover.spin_rover('right', duration=2.4)

    # Pause for 2 seconds
    rover.pause_rover(2)

    # Print rover status
    rover.status()

    # Close vehicle connection cleanly
    rover.close()

if __name__ == "__main__":
    main()

