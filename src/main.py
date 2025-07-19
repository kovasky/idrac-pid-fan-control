from helpers import load_env_config,get_slopes_and_intercepts,read_config_csv,write_config_csv
from pid import PID
from remote_management import RemoteManagement
from ntfy_sender import NTFY_Sender
import os
import logging
import sys
import time

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

def main():
    config = load_env_config()
    remote_management = RemoteManagement(config.host_addr, config.username, config.password)
    ntfy_sender = NTFY_Sender(config.ntfy_token, config.ntfy_host, config.ntfy_topic)

    consecutive_errors = 0
    max_consecutive_errors = 10

    if config.ntfy_test:
        try:
            ntfy_sender.send_message("iDrac 9 PID Fan Control Test", "Test message")
        except Exception as e:
            logger.error(f"Failed to send test notification: {e}")

    fan_speeds = []
    rpms = []
    slopes = []
    intercepts = []

    if config.scan:
        logger.info("Scanning fan speeds and RPMs...")
        try:
            scan_result = remote_management.scan(config.min_fan_speed_percent, config.max_fan_speed_percent)
            if not scan_result or scan_result == ([], []) or len(scan_result[0]) == 0:
                logger.error("Scan failed or returned no data.")
                ntfy_sender.send_message("iDrac 9 PID Fan Control", "Scan failed - using default values")
                fan_speeds = config.fan_speeds
                rpms = config.rpms
            else:
                fan_speeds, rpms = scan_result
                try:
                    write_config_csv(config.config_path, fan_speeds, rpms)
                except Exception as e:
                    logger.error(f"Failed to write config CSV: {e}")
        except Exception as e:
            logger.error(f"Scanning failed with exception: {e}")
            ntfy_sender.send_message("iDrac 9 PID Fan Control", f"Scanning failed: {e}")
            fan_speeds = config.fan_speeds
            rpms = config.rpms
    else:
        try:
            fan_speeds, rpms = read_config_csv(config.config_path)
        except Exception as e:
            logger.error(f"Failed to read config CSV: {e}")
            fan_speeds = []
            rpms = []

        if not fan_speeds or not rpms or len(fan_speeds) != len(rpms):
            fan_speeds = config.fan_speeds
            rpms = config.rpms
            logger.error("Could not load values from csv, using defaults.")

    if not fan_speeds or not rpms or len(fan_speeds) != len(rpms):
        logger.error("Invalid fan configuration - cannot proceed")
        ntfy_sender.send_message("iDrac 9 PID Fan Control", "Invalid fan configuration - exiting")
        sys.exit(1)

    slopes, intercepts = get_slopes_and_intercepts(fan_speeds, rpms)
    if not slopes or not intercepts:
        logger.error("Failed to calculate slopes and intercepts")
        ntfy_sender.send_message("iDrac 9 PID Fan Control", "Failed to calculate fan curves - exiting")
        sys.exit(1)

    try:
        pid = PID(
            desired_temp=config.desired_temp,
            k_proportional=config.kp,
            k_integral=config.ki,
            k_derivative=config.kd,
            fan_speeds=fan_speeds,
            rpms=rpms,
            slopes=slopes,
            intercepts=intercepts
        )
    except Exception as e:
        logger.error(f"Failed to initialize PID controller: {e}")
        ntfy_sender.send_message("iDrac 9 PID Fan Control", f"PID initialization failed: {e}")
        sys.exit(1)

    if config.disable_third_party_fan_mode:
        try:
            res = remote_management.disable_third_party_fan_mode()
            if res != 0:
                logger.error("Error disabling third party fan mode")
                ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error disabling third party fan mode")
        except Exception as e:
            logger.error(f"Exception disabling third party fan mode: {e}")
            ntfy_sender.send_message("iDrac 9 PID Fan Control", f"Exception disabling third party fan mode: {e}")

    manual_mode = False
    try:
        res = remote_management.enable_manual_fan_control()
        if res != 0:
            logger.error("Error setting fan control to manual")
            ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error setting fan control to manual")
            sys.exit(1)
        else:
            manual_mode = True
            logger.info("Manual fan control enabled successfully")
    except Exception as e:
        logger.error(f"Exception enabling manual fan control: {e}")
        ntfy_sender.send_message("iDrac 9 PID Fan Control", f"Exception enabling manual fan control: {e}")
        sys.exit(1)

    temp_threshold = config.max_temp - config.hysteresis
    logger.info("Starting PID fan control loop...")

    while True:
        loop_start_time = time.time()

        try:
            curr_temp = remote_management.get_highest_cpu_temperature()
            if curr_temp is None:
                consecutive_errors += 1
                logger.error(f"Failed to get temperature (error {consecutive_errors}/{max_consecutive_errors})")

                if consecutive_errors >= max_consecutive_errors:
                    logger.error("Too many consecutive temperature reading failures, exiting")
                    ntfy_sender.send_message("iDrac 9 PID Fan Control", "System exiting due to repeated temperature reading failures")
                    sys.exit(1)

                time.sleep(config.step_delay)
                continue

            consecutive_errors = 0

            if curr_temp > config.max_temp and manual_mode:
                logger.info(f"Temperature {curr_temp}°C exceeds maximum {config.max_temp}°C, switching to DELL fan control")
                ntfy_sender.send_message("iDrac 9 PID Fan Control", f"Temperature {curr_temp}°C exceeds maximum, switching to DELL fan control")

                try:
                    res = remote_management.enable_dell_fan_control()
                    if res != 0:
                        logger.error("Error setting DELL fan control")
                        ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error setting DELL fan control")
                        time.sleep(config.step_delay)
                        continue
                    manual_mode = False
                    logger.info("Successfully switched to DELL fan control")
                except Exception as e:
                    logger.error(f"Exception setting DELL fan control: {e}")
                    ntfy_sender.send_message("iDrac 9 PID Fan Control", f"Exception setting DELL fan control: {e}")
                    time.sleep(config.step_delay)
                    continue

            elif not manual_mode and curr_temp <= temp_threshold:
                logger.info(f"Temperature {curr_temp}°C below threshold {temp_threshold}°C, returning to manual fan control")

                try:
                    res = remote_management.enable_manual_fan_control()
                    if res != 0:
                        logger.error("Error returning to manual fan control after hysteresis")
                        ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error returning to manual fan control after hysteresis")
                        time.sleep(config.step_delay)
                        continue
                    manual_mode = True
                    ntfy_sender.send_message("iDrac 9 PID Fan Control", "Returned to manual fan control after hysteresis")
                    logger.info("Successfully returned to manual fan control")
                except Exception as e:
                    logger.error(f"Exception returning to manual fan control: {e}")
                    ntfy_sender.send_message("iDrac 9 PID Fan Control", f"Exception returning to manual fan control: {e}")
                    time.sleep(config.step_delay)
                    continue

            if manual_mode:
                try:
                    current_fan_speed_rpm = remote_management.get_current_fan_speed_rpm()
                    if current_fan_speed_rpm is None:
                        logger.error("Failed to get current fan speed, skipping PID step")
                        time.sleep(config.step_delay)
                        continue

                    new_fan_speed = pid.step(loop_start_time, curr_temp, current_fan_speed_rpm)
                    if new_fan_speed is None or new_fan_speed < 0:
                        logger.error("PID controller returned invalid fan speed")
                        time.sleep(config.step_delay)
                        continue

                    logger.info(f'Setting fan speed to {new_fan_speed}% (temp: {curr_temp}°C)')
                    res = remote_management.set_fan_speed_percent(new_fan_speed)
                    if res != 0:
                        logger.error(f"Error setting fan speed to {new_fan_speed}%")

                except Exception as e:
                    logger.error(f"Exception during PID control: {e}")
                    time.sleep(config.step_delay)
                    continue

            elif not manual_mode and curr_temp > temp_threshold:
                logger.info(f"In DELL mode, temperature {curr_temp}°C still above threshold {temp_threshold}°C")

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Unexpected error in main loop: {e}")

            if consecutive_errors >= max_consecutive_errors:
                logger.error("Too many consecutive errors, exiting")
                ntfy_sender.send_message("iDrac 9 PID Fan Control", f"System exiting due to repeated failures: {e}")
                sys.exit(1)

            time.sleep(config.step_delay)
            continue

        elapsed_time = time.time() - loop_start_time
        sleep_time = max(0, config.step_delay - elapsed_time)
        if sleep_time > 0:
            time.sleep(sleep_time)


if __name__ == "__main__":
    main()