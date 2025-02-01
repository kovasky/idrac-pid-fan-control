from helpers import required_env,parse_bool,get_slopes_and_intercepts,read_config_csv,write_config_csv
from pid import PID
from remote_management import RemoteManagement
import os
import logging
import sys

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    HOST_ADDR = required_env("HOST_ADDR")
    USER = required_env("USER")
    PASS = required_env("PASS")
    DESIRED_TEMP = required_env("DESIRED_TEMP")
    MAX_TEMP = required_env("MAX_TEMP")
    MIN_FAN_SPEED_PERCENT = required_env("MIN_FAN_SPEED_PERCENT")
    MAX_FAN_SPEED_PERCENT = required_env("MAX_FAN_SPEED_PERCENT")
    KP = required_env("KP")
    KI = required_env("KI")
    KD = required_env("KD")

    # Optional environment variables
    FAN_SPEEDS_ENV = os.environ.get("FAN_SPEEDS", "20,30,40,50,60") # These are my pre-recorded values
    RPMS_ENV = os.environ.get("FAN_RPMS", "1560,2040,2640,2880,3360")
    SCAN = parse_bool(os.environ.get("SCAN", "False"), default=False)
    DISABLE_THIRD_PARTY_FAN_MODE = parse_bool(os.environ.get("SCAN", "False"), default=False)
    CONFIG = os.environ.get("CONFIG", "/config/config.csv")

    try:
        desired_temp = int(DESIRED_TEMP)
        max_temp = int(MAX_TEMP)
        min_fan_speed_pct = int(MIN_FAN_SPEED_PERCENT)
        max_fan_speed_pct = int(MAX_FAN_SPEED_PERCENT)
        kp = float(KP)
        ki = float(KI)
        kd = float(KD)

        default_fan_speeds = list(map(int, FAN_SPEEDS_ENV.split(",")))
        default_rpms = list(map(int, RPMS_ENV.split(",")))
    except ValueError as exc:
        logger.error(f"Error converting environment variables to numeric values: {exc}")
        sys.exit(1)

    if len(default_fan_speeds) != len(default_rpms):
        logger.error("FAN_SPEEDS and FAN_RPMS must be the same length.")
        sys.exit(1)

    remote_management = RemoteManagement(HOST_ADDR, USER, PASS)
    
    fan_speeds=[]
    rpms=[]
    slopes=[]
    intercepts=[]
    if SCAN:
        logger.info("Scanning fan speeds and RPMs...")
        scan_result = remote_management.scan(min_fan_speed_pct, max_fan_speed_pct)
        if not scan_result or scan_result == (None, None):
            logger.error("Scan failed or returned no data.")
            sys.exit(1)
        fan_speeds, rpms = scan_result
        write_config_csv(CONFIG,fan_speeds,rpms)
    else:
        fan_speeds,rpms = read_config_csv(CONFIG)

        if not(fan_speeds) or not(rpms) or len(fan_speeds) is not len(rpms):
            fan_speeds = default_fan_speeds
            rpms = default_rpms
    
    slopes, intercepts = get_slopes_and_intercepts(fan_speeds, rpms)

    pid = PID(
        remote_management=remote_management,
        desired_temp=desired_temp,
        max_temp=max_temp,
        k_proportional=kp,
        k_integral=ki,
        k_derivative=kd,
        fan_speeds=fan_speeds,
        rpms=rpms,
        slopes=slopes,
        intercepts=intercepts
    )

    remote_management.disable_third_party_fan_mode()
    remote_management.enable_manual_fan_control()
    
    logger.info("Starting PID fan control loop...")
    while True:
        pid.step()
