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
    ntfy_sender = NTFY_Sender(config.ntfy_token,config.ntfy_host,config.ntfy_topic)

    if(config.ntfy_test == True):
        ntfy_sender.send_message("iDrac 9 PID Fan Control Test", "Test message")

    fan_speeds=[]
    rpms=[]
    slopes=[]
    intercepts=[]
    if config.scan:
        logger.info("Scanning fan speeds and RPMs...")
        scan_result = remote_management.scan(config.min_fan_speed_percent, config.max_fan_speed_percent)
        if not scan_result or scan_result == ([],[]):
            logger.error("Scan failed or returned no data.")
            sys.exit(1)
        fan_speeds, rpms = scan_result
        write_config_csv(config.config_path,fan_speeds,rpms)
    else:
        fan_speeds,rpms = read_config_csv(config.config_path)

        if not(fan_speeds) or not(rpms) or len(fan_speeds) != len(rpms):
            fan_speeds = config.fan_speeds
            rpms = config.rpms
            logger.error("Could not load values from csv, using defaults.")
    
    slopes, intercepts = get_slopes_and_intercepts(fan_speeds, rpms)

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

    if(config.disable_third_party_fan_mode == True):
        res = remote_management.disable_third_party_fan_mode()
        if(res != 0):
            logger.error("Error disabling third party fan mnode")
            ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error disabling third party fan mnode")

    res = remote_management.enable_manual_fan_control()
    if(res != 0):
        logger.error("Error setting fan control to manual")
        ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error setting fan control to manual")
        sys.exit(1)
    else:
        manual_mode = True
    
    temp_threshold = config.max_temp - config.hysteresis
    logger.info("Starting PID fan control loop...")
    while True:
        current_time = time.time()
        curr_temp = remote_management.get_highest_cpu_temperature()
        if(curr_temp > config.max_temp and manual_mode):
            logger.info("Temperature has gone over maximum, setting fan control mode to DELL")
            ntfy_sender.send_message("iDrac 9 PID Fan Control", "Temperature has gone over maximum, setting fan control mode to DELL")
            res = remote_management.enable_dell_fan_control()
            if res != 0:
                logger.error("Error setting DELL fan control")
                ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error setting DELL fan control")
                continue
            manual_mode = False      
        else:
            if(not manual_mode and curr_temp > temp_threshold):
                continue

            if(not manual_mode and curr_temp <= temp_threshold):
                res = remote_management.enable_manual_fan_control()
                ntfy_sender.send_message("iDrac 9 PID Fan Control", "Returning to manual fan control after hysteresis")
                if( res != 0):
                    logger.error("Error returning to manual fan control after hysteresis")
                    ntfy_sender.send_message("iDrac 9 PID Fan Control", "Error returning to manual fan control after hysteresis")
                    continue
                manual_mode = True

            new_fan_speed = pid.step(current_time, curr_temp,remote_management.get_current_fan_speed_rpm())
            logger.info(f'setting fan speed to {new_fan_speed}%')
            res = remote_management.set_fan_speed_percent(new_fan_speed)
            if(res != 0):
               logger.error("Error setting fan speed")
        time.sleep(max(0, config.step_delay - (time.time() - current_time)))

if __name__ == "__main__":
    main()