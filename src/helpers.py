import os
import logging
import sys
import csv
from dataclasses import dataclass

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

@dataclass
class EnvConfig:
    host_addr: str
    username: str
    password: str
    desired_temp: int
    max_temp: int
    min_fan_speed_percent: int
    max_fan_speed_percent: int
    kp: float
    ki: float
    kd: float
    fan_speeds: str
    rpms: str
    scan: bool
    disable_third_party_fan_mode: bool
    config_path: str
    step_delay: int
    hysteresis: int

def load_env_config() -> EnvConfig:
    """
    Loads and validates environment variables, returns an AppConfig dataclass instance.
    """
 
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
    DISABLE_THIRD_PARTY_FAN_MODE = parse_bool(os.environ.get("DISABLE_THIRD_PARTY_FAN_MODE", "False"), default=True)
    CONFIG = os.environ.get("CONFIG", "/config/config.csv")
    STEP_DELAY = os.environ.get("STEP_DELAY", 2)
    HYSTERESIS = os.environ.get("HYSTERESIS", 5)
    
    try:
        username = USER
        password = PASS
        desired_temp = int(DESIRED_TEMP)
        max_temp = int(MAX_TEMP)
        min_fan_speed_pct = int(MIN_FAN_SPEED_PERCENT)
        max_fan_speed_pct = int(MAX_FAN_SPEED_PERCENT)
        kp = float(KP)
        ki = float(KI)
        kd = float(KD)
        delay = int(STEP_DELAY)
        hysteresis = int(HYSTERESIS)

        default_fan_speeds = list(map(int, FAN_SPEEDS_ENV.split(",")))
        default_rpms = list(map(int, RPMS_ENV.split(",")))
    except ValueError as exc:
        logger.error(f"Error converting environment variables to numeric values: {exc}")
        sys.exit(1)

    if len(default_fan_speeds) != len(default_rpms):
        logger.error("FAN_SPEEDS and FAN_RPMS must be the same length.")
        sys.exit(1)
 
    return EnvConfig(
        host_addr=HOST_ADDR,
        username=username,
        password=password,
        desired_temp=desired_temp,
        max_temp=max_temp,
        min_fan_speed_percent=min_fan_speed_pct,
        max_fan_speed_percent=max_fan_speed_pct,
        kp=kp,
        ki=ki,
        kd=kd,
        fan_speeds=default_fan_speeds,
        rpms=default_rpms,
        scan=SCAN,
        disable_third_party_fan_mode=DISABLE_THIRD_PARTY_FAN_MODE,
        config_path=CONFIG,
        step_delay=delay,
        hysteresis=hysteresis,
    )

def parse_bool(env_val: str, default: bool = False) -> bool:
    """
    Checks if an environment variable is True or False.

    Returns True or False.
    """
    if env_val is None:
        return default
    return env_val.strip().lower() in ("true", "1", "yes")

def required_env(var_name: str) -> str:
    """
    Checks if environment variable exists or not.

    Exits on error.
    Returns the value if successful.
    """
    val = os.environ.get(var_name)
    if val is None:
        logger.error(f"Missing required environment variable: {var_name}")
        sys.exit(1)
    return val

def get_slopes_and_intercepts(fan_speeds : list[int], rpms: list[int]) -> tuple[list[float],list[float]]:
    """
    Calculates slopes and intercepts for percentage calculation.

    Returns ([],[]) if not succesful.
    Returns the calculated (slopes, intercepts) if successful.
    """
    if not fan_speeds or not rpms or len(fan_speeds) != len(rpms):
        return [],[]

    slopes=[]
    intercepts=[]
    for i in range(1,len(fan_speeds)):
        x1= rpms[i-1]
        x2= rpms[i]
        y1= fan_speeds[i-1]
        y2= fan_speeds[i]
        slope= (y2-y1)/(x2-x1)
        intercept= y1 - slope * x1
        slopes.append(slope)
        intercepts.append(intercept)
    
    return (slopes,intercepts)

def get_fan_speed_percent(rpm: int, fan_speeds: list[int], rpms: list[int], slopes: list[float], intercepts: list[float]) -> float:
    """
    Translates RPM to fan percentage based on interpolation.

    Returns -1 if conversion is not succesful.
    Returns the fan speed in percent if successful.
    """
    if rpm < rpms[0]:
        return fan_speeds[0]
    
    if rpm > rpms[-1]:
        return fan_speeds[-1]
    
    if rpm in rpms:
        return fan_speeds[rpms.index(rpm)]

    for i in range(1,len(rpms)):
        if rpm < rpms[i]:
            return slopes[i-1] * rpm + intercepts[i-1]

    return -1

def read_config_csv(config_path: str) -> tuple[list[int], list[int]]:
    """
    Reads fan speeds and RPMs from a 2-line CSV file:
    1st line: fan speeds (comma-delimited)
    2nd line: rpms (comma-delimited)

    Returns ([], []) if reading fails.
    Returns (fan_speeds,rpms) if reading successful.
    """
    try:
        with open(config_path) as file:
            reader = csv.reader(file, delimiter=",", quotechar='"')
            data = [row for row in reader]
    except Exception as e:
        logger.error(f"Error reading {config_path}: {e}")
        return [], []

    if len(data) < 2 or len(data[0]) != len(data[1]):
        logger.error(f"Malformed config file: need at least 2 lines in {config_path}.")
        return [], []

    return data[0], data[1]

def write_config_csv(config_path: str, fan_speeds: list[int], rpms: list[int]) -> None:
    """
    Writes fan speeds and RPMs to the CSV file, overwriting existing data.
    """
    logger.info(f"Writing fan speed config to {config_path}")
    try:
        with open(config_path, 'w', newline='\n') as file:
            writer = csv.writer(file)
            writer.writerow(fan_speeds)
            writer.writerow(rpms)
    except Exception as e:
        logger.error(f"Could not write to the config file {config_path}: {e}")
