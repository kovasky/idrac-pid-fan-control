from helpers import get_fan_speed_percent
import logging
import os

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

class PID: 
    def __init__(self, desired_temp: int, k_proportional : float, k_integral : float, k_derivative : float, 
                 fan_speeds : list[int], rpms: list [int], slopes: list[float], intercepts: list[float]):
        self.fan_speeds = fan_speeds
        self.rpms = rpms
        self.slopes = slopes
        self.intercepts = intercepts
        self.desired_temp = desired_temp
        self.min_fan_speed = fan_speeds[0]
        self.max_fan_speed =fan_speeds[-1]
        self.k_proportional = k_proportional
        self.k_integral = k_integral
        self.k_derivative = k_derivative
        self.last_run_time = 0
        self.integral_error = 0
        self.previous_error = 0
    
    def step(self, current_time : float, current_temp: int, current_fan_speed_rpm: int) -> int:
        """
        This performs a PID step and outputs the new fan speed in percentage
        """

        dt = current_time - self.last_run_time if self.last_run_time != 0 else 0
        self.last_run_time = current_time

        curr_fan_speed_percent = get_fan_speed_percent(current_fan_speed_rpm, self.fan_speeds,self.rpms,self.slopes,self.intercepts)
        error = current_temp - self.desired_temp
        self.integral_error += error * dt
        derivative_error = (error - self.previous_error) / dt if dt > 0 else 0
        pid_output = (self.k_proportional * error) + (self.k_integral * self.integral_error) + (self.k_derivative * derivative_error)
        output_fan_speed = round(curr_fan_speed_percent + pid_output)
        self.previous_error = error
        
        if (output_fan_speed < self.min_fan_speed):
            output_fan_speed = self.min_fan_speed
            self.previous_error = 0
            self.integral_error = 0
        elif (output_fan_speed > self.max_fan_speed):
            output_fan_speed = self.max_fan_speed
            self.previous_error = 0
            self.integral_error = 0
        
        logger.info(f'temp is {current_temp}, dt is {dt}, error is {error}, derror is {derivative_error} and ierror is {self.integral_error}')
        logger.info(f'new output fan speed is {output_fan_speed}%')
        return output_fan_speed
