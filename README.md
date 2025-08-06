# bb_mini_scales
Read and save weight data from the **M5Stack Unit Mini Scales (U177, I²C 0x26)** to daily CSV files.

## Hardware wiring (Raspberry Pi ↔︎ U177)
- **GND** (black)  → Pi GND (e.g. pin 6, 9, 14, …)
- **5V** (red)   → Pi 5V (pin 2 or 4)
- **SDA** (white)  → Pi SDA1 (pin 3, GPIO2)
- **SCL** (yellow)  → Pi SCL1 (pin 5, GPIO3)

> If `i2cdetect` does not show the device at **0x26**, swap SDA/SCL (it's easy to mix those).  
> The U177 blue LED briefly lights at power-up.

## Software setup (Raspberry Pi OS)

1) Enable I2C
```bash
sudo raspi-config       # Interface Options → I2C → Enable
sudo reboot
```

2) Install I2C tools (optional, for debugging) and Python deps
```bash
sudo apt update
sudo apt install -y i2c-tools python3-pip
pip3 install --upgrade smbus2
```

3) Ensure your user can access I2C
```bash
sudo usermod -aG i2c $USER
# log out/in or reboot for group change to take effect
```

4) Verify the device
```bash
i2cdetect -y 1
# Expect to see "26" in the table (address 0x26)
```

5) Get the code
```bash
git clone https://github.com/BioroboticsLab/bb_mini_scales
cd bb_mini_scales
```

6) Configure (optional)

Create a config.json (CLI flags override config values):
```json
{
  "data_dir": "/home/pi/scale_data",
  "bus": 1,
  "addr": "0x26",
  "interval": 1.0,
  "name": "scaleA",
  "print": false,
  "tare_on_start": true,
  "gap": null,
  "set_filters": false,
  "lp_filter_enabled": 1,
  "avg_filter_level": 10,
  "ema_filter_alpha": 10,
  "sign": 1.0
}
```

# Run

Basic
```bash
python3 mini_scale_logger.py
```

With config file
```bash
python3 mini_scale_logger.py -c config.json
```

Override config via CLI
```bash
python3 mini_scale_logger.py -c config.json --name scaleB --interval 1.0
```

What ```test_and_calibrate_scale.py``` does:
- Tare once, manually: Sends a hardware offset reset so the unloaded scale reads ~0 
- Optional calibration with a known weight: Guides you through placing a known mass and programs the GAP (counts/gram) into the device.
- Persistence: The GAP (calibration) is stored in non-volatile memory on the unit (survives power loss).
The tare/offset is not persistent—after a power cycle you should tare again (e.g., run the tool once, or press the unit’s button if you use button-triggered taring in your logger).

# Data info
Daily CSV files are written to data/ by default (or data_dir from config):

weight_data_[name_]YYYY-MM-DD.csv

Each line: 
Time, Weight_g, Weight_x100_g, RawADC

Note:  Measurements can simply use 'Weight_g'.  'Weight_x100_g' is the integer reading from the device; this and RawADC can be used to debug or error check if any values are off.


# Install as a system service

A sample unit file is included in the repo as mini_scale_logger.service:

```
# mini_scale_logger.service (example)
[Unit]
Description=MiniScale weight logger
After=network.target

[Service]
Type=simple
User=pi
Group=pi
WorkingDirectory=/home/pi/bb_mini_scales
ExecStart=/usr/bin/python3 /home/pi/bb_mini_scales/mini_scale_logger.py -c /home/pi/bb_mini_scales/config.json
Restart=always
RestartSec=2

[Install]
WantedBy=multi-user.target

```

Steps:
1.	Edit the file in the repo to match your paths, user, and Python:
	- User= / Group= (e.g., pi)
	- WorkingDirectory= (e.g., /home/pi/bb_mini_scales)
	- ExecStart= (ensure full paths to Python, script, and config)
	
2.	Install the service:

From the repo directory where mini_scale_logger.service lives:
```bash
sudo cp mini_scale_logger.service /etc/systemd/system/mini_scale_logger.service
sudo systemctl daemon-reload
```

3.	Enable on boot & start now:

```bash
sudo systemctl enable mini_scale_logger.service
sudo systemctl start mini_scale_logger.service
```

4.	Manage / inspect:
```bash
sudo systemctl status mini_scale_logger.service
sudo journalctl -u mini_scale_logger.service -f
sudo systemctl restart mini_scale_logger.service
sudo systemctl stop mini_scale_logger.service
sudo systemctl disable mini_scale_logger.service
```

Important: If you run the logger as a service and don’t want it to re-tare on every restart, set "tare_on_start": false in config.json. You can still tare manually (e.g., with test_and_calibrate_scale.py, or by pressing the unit’s button if your logger watches it).
