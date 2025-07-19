import subprocess
import re
import time
import logging
import os
from typing import Optional, Tuple

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL)
logger = logging.getLogger(__name__)

class RemoteManagement:
    """
    Controls fan settings and retrieves system status via ipmitool and racadm.
    """

    def __init__(self, host: str, username: str, password: str):
        base_command_ipmi = [
            "ipmitool",
            "-I", "lanplus",
            "-H", host,
            "-U", username,
            "-P", password
        ]
        self.command_sdr_temperature = base_command_ipmi + ["sdr", "type", "temperature"]
        self.command_sdr_fan1 = base_command_ipmi + ["sdr", "get", "Fan1"]
        self.command_set_fan_speed = base_command_ipmi + ["raw", "0x30", "0x30", "0x02", "0xff"]
        self.command_set_manual_fan_control = base_command_ipmi + ["raw", "0x30", "0x30", "0x01", "0x00"]
        self.command_set_dell_fan_control = base_command_ipmi + ["raw", "0x30", "0x30", "0x01", "0x01"]

        # For disabling the third-party PCIe fan mode via RACADM
        base_command_racadm = [
            "sshpass", "-p", password,
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-o", "ConnectTimeout=10",
            f"{username}@{host}",
            "racadm"
        ]
        self.command_get_pcie_slotlfm = base_command_racadm + ["get", "system.pcieslotlfm"]
        self.command_set_pcie_slotlfm = base_command_racadm + ["set", "placeholder", "disabled"]

    def _run_command_with_retry(self, command: list, max_retries: int = 3, delay: float = 1.0) -> Optional[subprocess.CompletedProcess]:
        """
        Run a command with retry logic to handle transient failures.
        """
        for attempt in range(max_retries):
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                if result.returncode == 0:
                    return result
                logger.warning(f"Command failed (attempt {attempt + 1}/{max_retries}): {' '.join(command)}")
                logger.warning(f"Error: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning(f"Command timed out (attempt {attempt + 1}/{max_retries}): {' '.join(command)}")
            except Exception as e:
                logger.warning(f"Command exception (attempt {attempt + 1}/{max_retries}): {e}")
            
            if attempt < max_retries - 1:
                time.sleep(delay)
        
        return None

    def enable_manual_fan_control(self) -> int:
        result = self._run_command_with_retry(self.command_set_manual_fan_control)
        if result is None or result.returncode != 0:
            error_msg = result.stderr if result else "Command failed after retries"
            logger.error(f"Failed to set manual fan control: {error_msg}")
            return 1
        return 0
                
    def enable_dell_fan_control(self) -> int:
        result = self._run_command_with_retry(self.command_set_dell_fan_control)
        if result is None or result.returncode != 0:
            error_msg = result.stderr if result else "Command failed after retries"
            logger.error(f"Failed to set dell fan control: {error_msg}")
            return 1
        return 0
        
    def get_highest_cpu_temperature(self) -> Optional[int]:
        """
        Reads temperature sensors via ipmitool, returns the highest CPU temperature found.
        Returns None if unable to get temperature.
        """
        result = self._run_command_with_retry(self.command_sdr_temperature)
        if result is None or result.returncode != 0:
            error_msg = result.stderr if result else "Command failed after retries"
            logger.error(f"Failed to run ipmitool for temperature: {error_msg}")
            return None

        try:
            temp_lines = [line for line in result.stdout.splitlines() if line.startswith("Temp")]
            if not temp_lines:
                logger.error("No temperature lines found in ipmitool output")
                return None
                
            temps_int = [int(line.split()[-3]) for line in temp_lines]
            if not temps_int:
                logger.error("No valid temperatures parsed from lines")
                return None
                
            temp_int = max(temps_int)
            return temp_int
        except (ValueError, IndexError) as e:
            logger.error(f"Could not parse temperature from lines: {e}")
            return None

    def get_current_fan_speed_rpm(self) -> Optional[int]:
        """
        Retrieves the fan speed in RPM via ipmitool.
        Returns None if unable to get fan speed.
        """
        result = self._run_command_with_retry(self.command_sdr_fan1)
        if result is None or result.returncode != 0:
            error_msg = result.stderr if result else "Command failed after retries"
            logger.error(f"Failed to run ipmitool for fan speed: {error_msg}")
            return None

        try:
            lines = result.stdout.splitlines()
            sensor_line = next((ln for ln in lines if "Sensor Reading" in ln), None)
            if not sensor_line:
                logger.error("No sensor reading found in ipmitool output")
                return None

            parts = re.split(r'[(:]', sensor_line)
            if len(parts) < 2:
                logger.error(f"Unexpected sensor line format: {sensor_line}")
                return None

            speed_str = parts[1].strip()
            return int(speed_str)
        except (ValueError, IndexError) as e:
            logger.error(f"Could not parse fan speed from line: {e}")
            return None

    def set_fan_speed_percent(self, speed: int) -> int:
        """
        Sets fan speed to a given percentage using ipmitool raw command.
        speed is integer 0-100.
        Returns 0 on success, 1 on failure.
        """
        if not 0 <= speed <= 100:
            logger.error(f"Invalid fan speed percentage: {speed}")
            return 1

        command = self.command_set_fan_speed + [hex(speed)]
        result = self._run_command_with_retry(command)
        if result is None or result.returncode != 0:
            error_msg = result.stderr if result else "Command failed after retries"
            logger.error(f"Failed to set fan speed: {error_msg}")
            return 1
        return 0

    def scan(self, min_fan_speed: int, max_fan_speed: int) -> Tuple[list[int], list[int]]:
        """
        Steps fan speed from min_fan_speed to max_fan_speed in increments of 10,
        waits 10 seconds each step, and records the RPM.
        Returns two lists: (fan_speed_percentages, corresponding_rpms).
        Resets fan speed to the initial setting afterward.
        """
        logger.info("Begin scanning")
        speeds = list(range(min_fan_speed, max_fan_speed+10, 10))
        rpms = []
        
        for s in speeds:
            if self.set_fan_speed_percent(s) != 0:
                logger.error(f"Failed to set fan speed during scan at {s}%")
                return [], []
                
            time.sleep(10)  # Let fans stabilize
            rpm_val = self.get_current_fan_speed_rpm()
            if rpm_val is None:
                logger.error(f'Error scanning, could not get fan rpm for percentage {s}')
                return [], []
                
            logger.info(f'RPM is {rpm_val} for percentage {s}')
            rpms.append(rpm_val)

        # Reset to initial speed
        if speeds and self.set_fan_speed_percent(speeds[0]) != 0:
            logger.error("Failed to reset fan speed after scan")
            return [], []

        return speeds, rpms

    def disable_third_party_fan_mode(self) -> int:
        """
        Disables the 'third-party PCIe card cooling response' on certain Dell systems.
        """
        result = self._run_command_with_retry(self.command_get_pcie_slotlfm)
        if result is None or result.returncode != 0:
            error_msg = result.stderr if result else "Command failed after retries"
            logger.error(f"Failed to run racadm to get PCIe slot LFM: {error_msg}")
            return 1

        pcie_lines = [line for line in result.stdout.splitlines() if "System.pcieslotlfm." in line]
        pcie_ports_count = len(pcie_lines)

        for i in range(1, pcie_ports_count + 1):
            temp_cmd = []
            for part in self.command_set_pcie_slotlfm:
                if part.lower() == "placeholder":
                    temp_cmd.append(f"system.pcieslotlfm.{i}.lfmmode")
                else:
                    temp_cmd.append(part)

            result = self._run_command_with_retry(temp_cmd)
            if result is None or result.returncode != 0:
                error_msg = result.stderr if result else "Command failed after retries"
                logger.error(f"Failed to disable third-party fan mode on slot {i}: {error_msg}")
            else:
                logger.info(f"Slot {i} third-party fan mode is now disabled.")
            
        return 0
