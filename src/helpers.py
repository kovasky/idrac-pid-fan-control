import os
import logging
import sys
import csv

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

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
    if not fan_speeds or not rpms or len(fan_speeds) is not len(rpms):
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

    if len(data) < 2:
        logger.error(f"Malformed config file: need at least 2 lines in {config_path}.")
        return [], []
    
    if len(data[0]) is not len(data[1]):
        logger.error(f"Malformed config file: need at least 2 lines in {config_path}.")
        return [],[]

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
