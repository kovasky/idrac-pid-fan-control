# iDrac 9 PID Fan Control

A Python-based PID controller for managing Dell server fan speeds. This script uses **ipmitool** to communicate with your iDrac controller in order to read CPU temperatures and set fan speeds accordingly. It also uses **racadm** to disable “third-party PCIe card cooling response” mode and allow fully manual fan control.

This was tested on iDrac 9 with firmware 3.30.30.30.

---

### Disclaimer

Use this tool at your own risk. Overridden fan speeds may lead to overheating if configured incorrectly. Always keep an eye on your server temperatures.

---

## Features

- **PID-based control**: for smooth and continuous fan speed adjustments.  
- **Optional scanning mode**: to map fan speed percentages to actual RPM values. The script cycles through a set of fan speeds and measures the corresponding RPM values to estimate a fan curve.
- **iDrac 9 compatible**: can disable “third-party PCIe” fan response mode so that fans do not go to full throttle when control returns to Dell’s profile. 
- **No third-party libraries**: all operations are performed using only the built-in libraries of Python.

---

## Running the program

### Locally

- **Python 3** (3.7+ recommended)  
- [ipmitool](https://github.com/ipmitool/ipmitool)  
- [sshpass](https://sourceforge.net/projects/sshpass/) (needed to run `racadm` commands on a Dell system)  

You are more than welcome to run this locally via a systemd service or some similar mechanism but there is also a pre-packaged docker image you can run. 

### Docker

- Docker must be installed on your system
- Create a folder to store the configuration file. Alternatively, you can use a volume.

#### Images

As of now, one docker image is available for this project:

- **ghcr.io/kovasky/idrac-pid-fan-control:latest**

#### Compose
Integrate these variables into your Docker Compose setup, for example with an `.env` file and a `docker-compose.yml` referencing it. Once environment variables are set, run:

```bash
docker compose up -d
```

---

## Environment Variables

These configure the PID controller, temperature targets, and scanning behavior.

### Required

| Variable                | Description                                                         |
| ----------------------- | ------------------------------------------------------------------- |
| `HOST_ADDR`             | IP or hostname of the server’s BMC (used by ipmitool commands)      |
| `USER`                  | BMC login username                                                  |
| `PASS`                  | BMC login password                                                  |
| `DESIRED_TEMP`          | Target CPU temperature in °C                                        |
| `MAX_TEMP`              | Safety threshold in °C (exceeding this reverts to default fan mode) |
| `MIN_FAN_SPEED_PERCENT` | Minimum allowable fan speed percentage                              |
| `MAX_FAN_SPEED_PERCENT` | Maximum allowable fan speed percentage                              |
| `KP`                    | Proportional gain (P) for the PID loop                              |
| `KI`                    | Integral gain (I) for the PID loop                                  |
| `KD`                    | Derivative gain (D) for the PID loop                                |

### Optional

| Variable                       | Default                    | Description                                                                                            |
| ------------------------------ | -------------------------- | ---------------------- |
| `FAN_SPEEDS`             | `20,30,40,50,60`           | Comma-separated list of fan speed percentages (used for scanning or default usage)                     |
| `FAN_RPMS`                     | `1560,2040,2640,2880,3360` | Comma-separated list of default RPM values correlating to `FAN_SPEEDS`                                 |
| `SCAN`                         | `False`                    | If `True`, script will scan fan speeds in increments of 10, measuring RPM to build\/update a config CSV |
| `DISABLE_THIRD_PARTY_FAN_MODE` | `False`                    | If `True`, attempts to disable Dell’s “third-party PCIe fan cooling” response |
| `CONFIG`                       | `/config/config.csv`       | CSV path for storing or reading fan speed → RPM mapping data                  |
| `STEP_DELAY`                   | `2`                        | Time delay (seconds) between each PID calculation step.                       |
| `LOG_LEVEL`                    | `INFO`                     | Logging verbosity; set to `DEBUG` for more detailed output                    |
| `HYSTERESIS`                   | `5`                        | Additional temperature margin in °C to reduce frequent fan speed changes      |
| `NTFY_TOKEN`                   | (none)                     | Ntfy push notifications token (if using push notifications)                   |
| `NTFY_HOST`                    | (none)                     | Ntfy.sh server hostname                                                       |
| `NTFY_TOPIC`                   | (none)                     | The target topic                                                              |
| `NTFY_TEST`                    | `False`                    | If `True`, sends a test notification                                          |

---

### Why did I build it?

Purely for fun. I made a bash script some time ago to bring down the noise level on my Dell T440 server, you can read about it [here](https://kovasky.me/blogs/fan_control/). This is an iteration to improve upon it.