#!/usr/bin/env python3
"""
test_scale.py

Basic sanity test for M5Stack Unit MiniScale using the corrected register map.
- Prints firmware, GAP, filters
- Tares
- Optionally performs 2-point GAP calibration with a known weight
- Streams weight from both 0x10 (float) and 0x60 (int/100) plus raw ADC

Run:
    python test_scale.py
"""

import time
from m5stack_mini_scale import MiniScale, DEFAULT_ADDR, DEFAULT_BUS


def maybe_calibrate(scale: MiniScale):
    ans = input("Calibrate GAP with known weight? [y/N]: ").strip().lower()
    if ans != "y":
        return
    print("Taring unit (reset offset)...")
    scale.tare()
    time.sleep(0.3)

    adc0 = scale.get_raw_adc()
    print(f"adc @ 0 g : {adc0}")

    input("Place known weight on the scale, wait for it to stabilize, then press Enter...")
    adcW = scale.get_raw_adc()
    print(f"adc @ weight: {adcW}")
    weight_g = float(input("Enter known weight in grams (e.g., 200): ").strip())

    gap = MiniScale.compute_gap_from_points(adc0, adcW, weight_g)
    print(f"Computed GAP = {gap:.6f} (ADC counts per gram)")
    scale.set_gap(gap)
    # Read back:
    readback = scale.get_gap()
    print(f"GAP readback = {readback:.6f}")


def main():
    with MiniScale(bus=DEFAULT_BUS, addr=DEFAULT_ADDR) as scale:
        print(f"FW version: {scale.get_fw_version()}")
        print(f"Current I2C addr: {hex(scale.get_i2c_address())}")
        try:
            gap = scale.get_gap()
            print(f"Current GAP: {gap:.6f}")
        except Exception as e:
            print(f"[WARN] Could not read GAP: {e}")

        lp, avg, ema = scale.get_filters()
        print(f"Filters -> lp_enabled={lp}, avg_level={avg}, ema_alpha={ema}")

        # Set a gentle average level for stability (optional)
        # scale.set_filters(avg_level=10, ema_alpha=10)

        print("Taring unit (reset offset)…")
        scale.tare()
        time.sleep(0.3)

        maybe_calibrate(scale)

        print("\nStreaming 30 samples:")
        for i in range(30):
            try:
                w_f = scale.get_weight_float()  # 0x10 (float grams)
                w_i = scale.get_weight_int()    # 0x60 (int/100 grams)
                adc = scale.get_raw_adc()
                print(f"{i:02d}: weight_f32={w_f:9.3f} g   weight_x100={w_i:9.3f} g   raw_adc={adc}")
            except Exception as e:
                print(f"{i:02d}: read error -> {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()