import subprocess
import re
import time
import logging
import os

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
        self.command_set_dell_fan_controll = base_command_ipmi + ["raw", "0x30", "0x30", "0x01", "0x01"]

        # For disabling the third-party PCIe fan mode via RACADM
        base_command_racadm = [
            "sshpass", "-p", password,
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            f"{username}@{host}",
            "racadm"
        ]
        self.command_get_pcie_slotlfm = base_command_racadm + ["get", "system.pcieslotlfm"]
        # Will replace "placeholder" on-the-fly when disabling third-party fan mode
        self.command_set_pcie_slotlfm = base_command_racadm + ["set", "placeholder", "disabled"]

    def enable_manual_fan_control(self) -> int:
        result = subprocess.run(self.command_set_manual_fan_control, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Failed to set manual fan control:", result.stderr)
        return result.returncode
                
    def enable_dell_fan_control(self) -> int:
        result = subprocess.run(self.command_set_dell_fan_controll, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Failed to set dell fan control:", result.stderr)
        return result.returncode
        
    def get_highest_cpu_temperature(self) -> int:
        """
        Reads temperature sensors via ipmitool, returns the highest CPU temperature found.
        """
        result = subprocess.run(self.command_sdr_temperature, capture_output=True, text=True)
        if result.returncode != 0:
            print("Failed to run ipmitool:", result.stderr)
            return result.returncode

        temp_lines = [line for line in result.stdout.splitlines() if line.startswith("Temp")]
        temps_int = [int(line.split()[-3]) for line in temp_lines]
        try:
            temp_int = max(temps_int)
            return temp_int if temp_int else None
        except ValueError:
            print("Could not parse temperature from lines:", temp_lines)
            return None

    def get_current_fan_speed_rpm(self) -> int:
        """
        Retrieves the fan speed in RPM via ipmitool.
        """
        result = subprocess.run(self.command_sdr_fan1, capture_output=True, text=True)
        if result.returncode != 0:
            print("Failed to run ipmitool:", result.stderr)
            return None

        lines = result.stdout.splitlines()
        sensor_line = next((ln for ln in lines if "Sensor Reading" in ln), None)
        if not sensor_line:
            print("No sensor reading found in ipmitool output.")
            return None

        parts = re.split(r'[(:]', sensor_line)
        if len(parts) < 2:
            print("Unexpected sensor line format:", sensor_line)
            return None

        speed_str = parts[1].strip()
        try:
            return int(speed_str)
        except ValueError:
            print("Could not parse fan speed integer from line:", sensor_line)
            return None

    def set_fan_speed_percent(self, speed: int) -> int:
        """
        Sets fan speed to a given percentage using ipmitool raw command.
        speed is integer 0-100.
        Returns the command's return code, or None if it fails.
        """

        command = self.command_set_fan_speed + [hex(speed)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            print("Failed to run ipmitool:", result.stderr)
        return result.returncode

    def scan(self, min_fan_speed: int, max_fan_speed: int) -> tuple[list[int], list[int]]:
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
            command = self.command_set_fan_speed + [hex(s)]
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                print("Failed to run ipmitool:", result.stderr)
                return None, None
            time.sleep(10)  # Let fans stabilize
            rpm_val = self.get_current_fan_speed_rpm()
            if not rpm_val: 
                logger.error(f'Error scanning, could not get fan rpm for percentage {s}')
                return None, None
            logger.info(f'RPM is {rpm_val} for percentage {s}')
            rpms.append(rpm_val if rpm_val else 0)

        if speeds:
            reset_command = self.command_set_fan_speed + [hex(speeds[0])]
            result = subprocess.run(reset_command, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error("Failed to run ipmitool during reset:", result.stderr)
                return None, None

        return speeds, rpms

    def disable_third_party_fan_mode(self) -> int:
        """
        Disables the 'third-party PCIe card cooling response' on certain Dell systems
        by iterating over PCIe slots and setting the LFM mode to 'disabled' via RACADM.
        """
        result = subprocess.run(self.command_get_pcie_slotlfm, capture_output=True, text=True)
        if result.returncode != 0:
            print("Failed to run racadm to get PCIe slot LFM:", result.stderr)
            return result.returncode

        pcie_lines = [line for line in result.stdout.splitlines() if "System.pcieslotlfm." in line]
        pcie_ports_count = len(pcie_lines)

        for i in range(1, pcie_ports_count + 1):
            temp_cmd = []
            for part in self.command_set_pcie_slotlfm:
                if part.lower() == "placeholder":
                    temp_cmd.append(f"system.pcieslotlfm.{i}.lfmmode")
                else:
                    temp_cmd.append(part)

            result = subprocess.run(temp_cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Failed to disable third-party fan mode on slot {i}:", result.stderr)
            else:
                logger.info(f"Slot {i} third-party fan mode is now disabled.")
            
        return result.returncode
