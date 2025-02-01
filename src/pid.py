from remote_management import RemoteManagement
from helpers import get_fan_speed_percent
import time
import logging
import os

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

class PID: 
    def __init__(self, remote_management: RemoteManagement, desired_temp: int, max_temp: int, k_proportional : float, k_integral : float, k_derivative : float, 
                 fan_speeds : list[int], rpms: list [int], slopes: list[float], intercepts: list[float]):
        self.fan_speeds = fan_speeds
        self.rpms = rpms
        self.slopes = slopes
        self.intercepts = intercepts
        self.remote_management = remote_management
        self.desired_temp = desired_temp
        self.max_temp = max_temp
        self.min_fan_speed = fan_speeds[0]
        self.max_fan_speed =fan_speeds[-1]
        self.k_proportional = k_proportional
        self.k_integral = k_integral
        self.k_derivative = k_derivative
        self.last_run_time = 0
        self.integral_error = 0
        self.previous_error = 0
    
    def step(self):
        """
        This performs a PID step. It gathers the CPU temperature 4 times, as I've found readings
        to vary greatly, within one call from one another. This tries to normalize those readings.
        """
        current_time = time.time()
        dt = current_time - self.last_run_time if self.last_run_time != 0 else 0
        self.last_run_time = current_time

        curr_temp = self.remote_management.get_highest_cpu_temperature()
        if(curr_temp > self.max_temp):
            logger.info("Temperature has gone over maximum, setting fan control mode to DELL")
            res = self.remote_management.enable_dell_fan_control()
            if res != 0:
                logger.error("Error setting DELL fan control")
                return

        curr_fan_speed = get_fan_speed_percent(self.remote_management.get_current_fan_speed_rpm(), self.fan_speeds,self.rpms,self.slopes,self.intercepts)
        error = curr_temp - self.desired_temp
        self.integral_error += error * dt
        derivative_error = (error - self.previous_error) / dt if dt > 0 else 0
        pid_output = (self.k_proportional * error) + (self.k_integral * self.integral_error) + (self.k_derivative * derivative_error)
        output_fan_speed = curr_fan_speed + pid_output
        self.previous_error = error
        
        if (output_fan_speed < self.min_fan_speed):
            output_fan_speed = self.min_fan_speed
            self.previous_error = 0
            self.integral_error = 0
        elif (output_fan_speed > self.max_fan_speed):
            output_fan_speed = self.max_fan_speed
            self.previous_error = 0
            self.integral_error = 0
        
        logger.info(f'setting fan speed to {output_fan_speed}%')
        logger.info(f'temp is {curr_temp}, dt is {dt}, error is {error}, derror is {derivative_error} and ierror is {self.integral_error}')
        self.remote_management.set_fan_speed_percent(round(output_fan_speed,1))
