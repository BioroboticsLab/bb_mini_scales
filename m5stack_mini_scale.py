#!/usr/bin/env python3
"""
m5stack_mini_scale.py

Tiny Python driver for the M5Stack Unit MiniScale (U177).
Implements the I²C register map (addr 0x26) exactly as documented.

- All multi-byte values are LITTLE-ENDIAN.
- Preferred weight reads:
    * 0x10 -> float32 grams
    * 0x60 -> int32 WeightX100 (grams = value/100)

Requires:
    pip install smbus2
"""

from __future__ import annotations

import struct
from typing import Optional, Tuple
from smbus2 import SMBus


# --------- I2C defs ----------
DEFAULT_BUS = 1
DEFAULT_ADDR = 0x26

# Registers (from protocol sheet)
REG_RAW_ADC         = 0x00  # int32 LE
REG_WEIGHT_F32      = 0x10  # float32 LE grams
REG_BUTTON          = 0x20  # 0 = pressed, 1 = not pressed
REG_LED_RGB         = 0x30  # 3 bytes [R,G,B]
REG_GAP_F32         = 0x40  # float32 LE (ADC counts per gram)
REG_OFFSET_TARE     = 0x50  # write 1 to reset/tare
REG_WEIGHT_X100_I32 = 0x60  # int32 LE; grams = value/100
REG_WEIGHT_STR      = 0x70  # up to 15 chars + '\0'
REG_FILTERS         = 0x80  # 3 bytes: lp_enabled, avg_level (0..50), ema_alpha (0..99)
REG_FW_VERSION      = 0xFE  # 1 byte (per M5 Arduino lib)
REG_I2C_ADDRESS     = 0xFF  # 1 byte R/W (per M5 Arduino lib)


class MiniScale:
    def __init__(self, bus: int = DEFAULT_BUS, addr: int = DEFAULT_ADDR):
        self.addr = int(addr)
        self._bus = SMBus(int(bus))

    # ---- context manager / cleanup ----
    def close(self):
        try:
            self._bus.close()
        except Exception:
            pass

    def __enter__(self) -> "MiniScale":
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ---- low-level helpers ----
    def _read_block(self, reg: int, n: int) -> bytes:
        data = self._bus.read_i2c_block_data(self.addr, reg, n)
        return bytes(data)

    def _write_block(self, reg: int, data: bytes | list[int]) -> None:
        if isinstance(data, bytes):
            payload = list(data)
        else:
            payload = list(data)
        self._bus.write_i2c_block_data(self.addr, reg, payload)

    # ---- core reads ----
    def get_raw_adc(self) -> int:
        """Raw ADC, int32 LE."""
        b = self._read_block(REG_RAW_ADC, 4)
        return int.from_bytes(b, "little", signed=True)

    def get_weight_float(self) -> float:
        """Weight in grams as float32 from 0x10."""
        b = self._read_block(REG_WEIGHT_F32, 4)
        return struct.unpack("<f", b)[0]

    def get_weight_int(self) -> float:
        """Weight in grams via 0x60 (int32 weight*100)."""
        b = self._read_block(REG_WEIGHT_X100_I32, 4)
        val = int.from_bytes(b, "little", signed=True)
        return val / 100.0

    def get_weight(self, prefer: str = "float") -> float:
        """
        Convenience: read weight in grams.
        prefer = 'float' (0x10) or 'int' (0x60)
        """
        if prefer == "int":
            return self.get_weight_int()
        return self.get_weight_float()

    # ---- tare / calibration (GAP) ----
    def tare(self) -> None:
        """Write 1 to 0x50 to reset offset on the unit."""
        self._write_block(REG_OFFSET_TARE, [1])

    def get_gap(self) -> float:
        """Read GAP (float32 LE) used by the device’s internal calibration."""
        b = self._read_block(REG_GAP_F32, 4)
        return struct.unpack("<f", b)[0]

    def set_gap(self, gap: float) -> None:
        """Set GAP (float32 LE) — ADC counts per gram."""
        self._write_block(REG_GAP_F32, struct.pack("<f", float(gap)))

    @staticmethod
    def compute_gap_from_points(adc_0g: int, adc_w: int, weight_g: float) -> float:
        """
        GAP = (adc_0g - adc_w) / weight_g
        (we swap the subtraction so that if adc_w < adc_0g, GAP > 0)
        """
        if weight_g == 0:
            raise ValueError("weight_g must be non-zero")
        return (int(adc_0g) - int(adc_w)) / float(weight_g)

    # ---- LED / button / filters ----
    def set_led(self, r: int, g: int, b: int) -> None:
        self._write_block(REG_LED_RGB, [r & 0xFF, g & 0xFF, b & 0xFF])

    def get_led(self) -> tuple[int, int, int]:
        data = self._read_block(REG_LED_RGB, 3)
        return data[0], data[1], data[2]

    def get_button_pressed(self) -> bool:
        """True when pressed (register returns 0 for press)."""
        v = self._read_block(REG_BUTTON, 1)[0]
        return (v == 0)

    def set_filters(self, lp_enabled: Optional[int] = None,
                    avg_level: Optional[int] = None,
                    ema_alpha: Optional[int] = None) -> None:
        """
        Write any subset of the filter bytes.
        lp_enabled: 0/1 (default 1)
        avg_level : 0..50 (default 10)
        ema_alpha : 0..99 (default 10)
        """
        # Read current, modify, then write back to avoid clobbering other fields
        cur = list(self._read_block(REG_FILTERS, 3))
        if lp_enabled is not None:
            cur[0] = int(lp_enabled) & 0xFF
        if avg_level is not None:
            cur[1] = int(avg_level) & 0xFF
        if ema_alpha is not None:
            cur[2] = int(ema_alpha) & 0xFF
        self._write_block(REG_FILTERS, cur)

    def get_filters(self) -> Tuple[int, int, int]:
        b = self._read_block(REG_FILTERS, 3)
        return b[0], b[1], b[2]

    # ---- misc ----
    def get_weight_str(self) -> str:
        b = self._read_block(REG_WEIGHT_STR, 16)
        return b.split(b"\x00", 1)[0].decode(errors="ignore")

    def get_fw_version(self) -> int:
        return self._read_block(REG_FW_VERSION, 1)[0]

    def get_i2c_address(self) -> int:
        return self._read_block(REG_I2C_ADDRESS, 1)[0]

    def set_i2c_address(self, new_addr: int) -> int:
        self._write_block(REG_I2C_ADDRESS, [int(new_addr) & 0x7F])
        self.addr = int(new_addr) & 0x7F
        return self.addr