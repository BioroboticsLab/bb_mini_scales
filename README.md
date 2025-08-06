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
  "interval": 1,
  "no_tare": false,
  "print": true,
  "name": "scaleA",
  "calibration_mass_grams": 1000,
  "calibration_mass_val": 1000
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

# Data info
Daily CSV files are written to data/ by default (or data_dir from config):

weight_data_[name_]YYYY-MM-DD.csv

Each line: Time,Weight_g

Optional: install as a system service

This lets the logger start automatically on boot.

# Setting up system service
from the repo root:
```bash
chmod +x setup_system_service.sh
sudo ./setup_system_service.sh \
  --user pi \
  --workdir /home/pi/bb_mini_scales \
  --python /usr/bin/python3 \
  --config /home/pi/bb_mini_scales/config.json \
  --print
```

Manage the service:

sudo systemctl restart mini_scale_logger.service
sudo systemctl stop mini_scale_logger.service
sudo systemctl enable mini_scale_logger.service   # start on boot
sudo systemctl disable mini_scale_logger.service
sudo systemctl status mini_scale_logger.service


# Notes
- Readings are returned in grams, based on the calibration factor.
- You will need to determine the calibration factor using a weight of known mass.  This is the difference in the sensor value before/after the weight is placed on.  Use 'test_scale.py' for a simple way to just read a few values
- The logger performs a tare on startup by default. Use --no-tare to disable.

