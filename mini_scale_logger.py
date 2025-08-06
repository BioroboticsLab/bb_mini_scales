#!/usr/bin/env python3
"""
mini_scale_logger.py

Log weight from the M5Stack Unit MiniScale (U177, I2C 0x26) to daily CSV files.
Uses the high-level helpers in m5stack_mini_scale.py (MiniScale).

CSV schema (one file per day, name tag optional):
    Time,Weight_g,Weight_x100_g,RawADC
    2025-08-05T12:34:56.789012,12.345,12.34,9136487

Examples:
    python mini_scale_logger.py -c config.json --print
    python mini_scale_logger.py --name scaleA --addr 0x26 --interval 1.0

Notes:
- This logger always enables "tare on button press": if the Unit’s button is pressed,
  it will call scale.tare() immediately (with debounce). This is independent of config.
"""

import os
import csv
import time
import json
import argparse
import signal
from datetime import datetime

from m5stack_mini_scale import MiniScale, DEFAULT_ADDR, DEFAULT_BUS


# --------------------
# Defaults / Constants
# --------------------
DEFAULTS = {
    "data_dir": "data",
    "bus": DEFAULT_BUS,
    "addr": hex(DEFAULT_ADDR),  # hex string or int
    "interval": 1.0,            # seconds
    "name": "",
    "print": False,
    "tare_on_start": False,     # recommended False for services; button-tare is always active
    "gap": None,                # if provided, write GAP (counts/gram) on start
    "set_filters": False,       # if True, apply the three filter params below
    "lp_filter_enabled": 1,     # 0/1
    "avg_filter_level": 10,     # 0..50
    "ema_filter_alpha": 10,     # 0..99
    "sign": 1.0                 # multiply final grams by this (use -1 if your unit reads negative)
}

# Button-tare debounce settings
BTN_SAMPLE_SECS = 0.05    # polling period for the button inside the loop
BTN_AFTER_TARE_SLEEP = 0.30  # short pause after tare
BTN_WAIT_RELEASE = True      # wait for button release before accepting another tare


# ------------
# Graceful exit
# ------------
_stop = False
def _handle_sigterm(signum, frame):
    global _stop
    _stop = True

signal.signal(signal.SIGINT, _handle_sigterm)
signal.signal(signal.SIGTERM, _handle_sigterm)


# -----------------
# Helpers
# -----------------
def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)

def sanitize_tag(tag: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (tag or ""))

def today_path(data_dir: str, name: str) -> str:
    day = datetime.now().strftime("%Y-%m-%d")
    tag = sanitize_tag(name)
    base = f"weight_data_{tag + '_' if tag else ''}{day}.csv"
    return os.path.join(data_dir, base)

def ensure_header(fp, writer: csv.writer) -> None:
    fp.seek(0, os.SEEK_END)
    needs = fp.tell() == 0
    if not needs:
        fp.seek(0)
        first = fp.readline()
        needs = ("Time,Weight_g,Weight_x100_g,RawADC" not in first)
        fp.seek(0, os.SEEK_END)
    if needs:
        writer.writerow(["Time", "Weight_g", "Weight_x100_g", "RawADC"])
        fp.flush()

def load_config(path: str | None) -> dict:
    if not path:
        return {}
    with open(path, "r") as f:
        cfg = json.load(f)
    if not isinstance(cfg, dict):
        raise ValueError("Config JSON must be an object.")
    return cfg

def coerce_addr(addr_any) -> int:
    if isinstance(addr_any, str):
        return int(addr_any, 0)
    return int(addr_any)


# -------
# Main
# -------
def main():
    # Pre-parse only -c for config path
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("-c", "--config", default=None)
    pre_args, _ = pre.parse_known_args()

    cfg = {**DEFAULTS, **load_config(pre_args.config)}

    parser = argparse.ArgumentParser(description="Log weight from M5Stack U177 to daily CSVs.")
    parser.add_argument("-c", "--config", default=pre_args.config, help="Path to JSON config")
    parser.add_argument("--data-dir", default=cfg["data_dir"])
    parser.add_argument("--bus", type=int, default=cfg["bus"])
    parser.add_argument("--addr", default=cfg["addr"], help="I2C address (e.g. 0x26)")
    parser.add_argument("--interval", type=float, default=cfg["interval"])
    parser.add_argument("--name", default=cfg["name"])
    parser.add_argument("--print", action="store_true", default=cfg["print"])
    parser.add_argument("--tare-on-start", action="store_true", default=cfg["tare_on_start"])
    parser.add_argument("--gap", type=float, default=cfg["gap"],
                        help="If provided, write GAP (counts/gram) on start.")
    parser.add_argument("--set-filters", action="store_true", default=cfg["set_filters"])
    parser.add_argument("--lp-filter-enabled", type=int, default=cfg["lp_filter_enabled"])
    parser.add_argument("--avg-filter-level", type=int, default=cfg["avg_filter_level"])
    parser.add_argument("--ema-filter-alpha", type=int, default=cfg["ema_filter_alpha"])
    parser.add_argument("--sign", type=float, default=cfg["sign"],
                        help="Multiply final grams by this (use -1 for inverted sign).")
    args = parser.parse_args()

    addr = coerce_addr(args.addr)
    ensure_dir(args.data_dir)

    # Open scale
    scale = MiniScale(bus=args.bus, addr=addr)

    # Optional: configure GAP and filters
    if args.gap is not None:
        try:
            scale.set_gap(args.gap)
        except Exception as e:
            print(f"[WARN] set_gap failed: {e}")

    if args.set_filters:
        try:
            scale.set_filters(
                lp_enabled=int(args.lp_filter_enabled),
                avg_level=int(args.avg_filter_level),
                ema_alpha=int(args.ema_filter_alpha),
            )
        except Exception as e:
            print(f"[WARN] set_filters failed: {e}")

    # Optional one-time tare on startup (be careful if load is present)
    if args.tare_on_start:
        try:
            print("Taring unit (reset offset)…")
            scale.tare()
            time.sleep(0.2)
        except Exception as e:
            print(f"[WARN] tare on start failed: {e}")

    # Prepare CSV
    current_path = today_path(args.data_dir, args.name)
    fp = open(current_path, "a+", newline="")
    writer = csv.writer(fp)
    ensure_header(fp, writer)

    # Button tare state
    prev_pressed = False

    try:
        last_sample_time = 0.0
        while not _stop:
            # rotate at midnight
            new_path = today_path(args.data_dir, args.name)
            if new_path != current_path:
                fp.close()
                current_path = new_path
                fp = open(current_path, "a+", newline="")
                writer = csv.writer(fp)
                ensure_header(fp, writer)

            ts = datetime.now().isoformat()

            # ---- Read weights ----
            try:
                # get_weight_float() -> grams (float32 from 0x10)
                g_f32 = scale.get_weight_float() * args.sign
                # get_weight_int() -> grams (int/100 from 0x60, already divided inside driver)
                g_i = scale.get_weight_int() * args.sign
                adc = scale.get_raw_adc()
            except Exception as e:
                print(f"[WARN] read failed: {e}")
                g_f32 = float("nan")
                g_i = float("nan")
                adc = -1

            writer.writerow([ts, f"{g_f32:.3f}", f"{g_i:.3f}", adc])
            fp.flush()

            if args.print:
                print(f"{ts}  {g_f32:.3f} g (x100:{g_i:.3f} g)  adc:{adc}")

            # ---- Button-triggered tare (always active) ----
            # Poll the button at a faster cadence than the sample interval
            now = time.time()
            if now - last_sample_time >= BTN_SAMPLE_SECS:
                last_sample_time = now
                try:
                    pressed = scale.get_button_pressed()  # True if pressed
                except Exception:
                    pressed = False

                # Rising edge: pressed now, not pressed before
                if pressed and not prev_pressed:
                    try:
                        scale.tare()
                        if args.print:
                            print(f"{datetime.now().isoformat()}  [INFO] Button press detected -> tare()")
                        time.sleep(BTN_AFTER_TARE_SLEEP)
                        if BTN_WAIT_RELEASE:
                            # Wait until user releases the button before allowing another tare
                            while True:
                                try:
                                    if not scale.get_button_pressed():
                                        break
                                except Exception:
                                    break
                                time.sleep(BTN_SAMPLE_SECS)
                    except Exception as e:
                        print(f"[WARN] button-tare failed: {e}")

                prev_pressed = pressed

            # Sleep until next reading (but keep the loop responsive for button checks)
            time.sleep(max(0.0, args.interval - BTN_SAMPLE_SECS))
    finally:
        fp.close()
        scale.close()


if __name__ == "__main__":
    main()