#!/usr/bin/env python3
"""
test_hcsr04.py — Verifies live HC-SR04 readings from MSDA_Firmware_USB over USB Serial.

Usage:
    python test_hcsr04.py [--port COM9] [--duration 15] [--baudrate 115200]

Exit codes:
    0 — PASSED (at least 3 DATA messages received)
    1 — FAILED (no messages or serial error)
"""

import argparse
import re
import sys
import time

# Try to import serial; guide user if not installed
try:
    import serial
except ImportError:
    print("[ERROR] pyserial not installed. Run: pip install pyserial")
    sys.exit(1)

# ── Argument parsing ───────────────────────────────────────────────
parser = argparse.ArgumentParser(description="MSDA HC-SR04 USB Serial Test")
parser.add_argument("--port",     default="COM9",   help="Serial port (default: COM9)")
parser.add_argument("--baudrate", default=115200,   type=int)
parser.add_argument("--duration", default=15,       type=int, help="Test duration in seconds")
parser.add_argument("--min-readings", default=3,    type=int, dest="min_readings",
                    help="Minimum HC-SR04 readings required to PASS")
args = parser.parse_args()

# ── Regex: matches <TYPE|timestamp_ms|content> protocol ───────────
MSG_RE = re.compile(r"<([A-Z]+)\|(\d+)\|([^>]*)>")
# Specifically for HC-SR04 DATA messages: HC_SR04,12.34,raw_us=720
HCSR04_RE = re.compile(r"HC_SR04,([\d.]+),raw_us=(\d+)")
DHT11_RE = re.compile(r"DHT11,([\w.]+),([\w.]+)")
PIR_RE = re.compile(r"PIR,(\d+)")

print(f"\n{'='*55}")
print(f"  MSDA HC-SR04 USB Serial Test")
print(f"  Port: {args.port}  |  Baud: {args.baudrate}  |  Duration: {args.duration}s")
print(f"{'='*55}\n")

# ── Open port ─────────────────────────────────────────────────────
try:
    ser = serial.Serial(
        port=args.port,
        baudrate=args.baudrate,
        timeout=1.0
    )
    print(f"[OK] Opened {args.port}")
except serial.SerialException as e:
    print(f"[ERROR] Cannot open {args.port}: {e}")
    print("       Is the Arduino plugged in and on the correct COM port?")
    sys.exit(1)

# Wait for Arduino to reset after port open
time.sleep(2.0)
print("[..] Waiting for boot message ...\n")

# ── Read loop ─────────────────────────────────────────────────────
buffer        = ""
readings_hcsr = []        # list of (dist_cm, raw_us)
readings_dht  = []        # list of (temp, hum)
readings_pir  = []        # list of (motion)
got_boot      = False
start_time    = time.time()

try:
    while time.time() - start_time < args.duration:
        raw = ser.read(ser.in_waiting or 1)
        if raw:
            buffer += raw.decode("utf-8", errors="ignore")

        # Extract complete <...> messages
        for m in MSG_RE.finditer(buffer):
            msg_type, ts, content = m.group(1), m.group(2), m.group(3)

            if msg_type == "STATUS" and not got_boot:
                got_boot = True
                print(f"[OK] STATUS  @ {ts}ms : {content}")

            elif msg_type == "HEARTBEAT":
                print(f"[  ] HEARTBEAT @ {ts}ms : {content}")

            elif msg_type == "INVENTORY":
                print(f"[  ] INVENTORY @ {ts}ms : {content}")

            elif msg_type == "DATA":
                hm = HCSR04_RE.search(content)
                dm = DHT11_RE.search(content)
                pm = PIR_RE.search(content)

                if hm:
                    dist_cm = float(hm.group(1))
                    raw_us  = int(hm.group(2))
                    readings_hcsr.append((dist_cm, raw_us))
                    tag = "WARN: timeout (0 cm — check wiring?)" if dist_cm == 0.0 else "OK"
                    print(f"[{tag[:2]}] HC_SR04  @ {ts}ms : {dist_cm:.2f} cm  (raw_us={raw_us})")
                elif dm:
                    t, h = dm.group(1), dm.group(2)
                    readings_dht.append((t, h))
                    tag = "WA" if t == "ERROR" else "OK"
                    print(f"[{tag}] DHT11    @ {ts}ms : Temp={t}C, Humidity={h}%")
                elif pm:
                    m = int(pm.group(1))
                    readings_pir.append(m)
                    tag = "MO" if m else "--"
                    print(f"[{tag}] PIR      @ {ts}ms : Motion={'DETECTED' if m else 'None'}")

        # Trim consumed messages from buffer to avoid re-matching
        last_close = buffer.rfind(">")
        if last_close >= 0:
            buffer = buffer[last_close + 1:]

except KeyboardInterrupt:
    print("\n[..] Interrupted by user")

finally:
    ser.close()

# ── Result ────────────────────────────────────────────────────────
print(f"\n{'='*55}")
print(f"  Results")
print(f"{'='*55}")
print(f"  Boot message received : {'YES' if got_boot else 'NO'}")
print(f"  HC-SR04 readings      : {len(readings_hcsr)} of {args.min_readings} required")
print(f"  DHT11 readings        : {len(readings_dht)}")
print(f"  PIR   readings        : {len(readings_pir)}")

if readings_hcsr:
    dists = [r[0] for r in readings_hcsr]
    print(f"  HC-SR04 Range         : {min(dists):.2f} – {max(dists):.2f} cm")
    if all(d == 0.0 for d in dists):
        print("  [WARN] All HC-SR04 readings are 0.00 cm — Not wired or blocked.")

if len(readings_hcsr) >= args.min_readings:
    print(f"\n  ✔  PASSED — received data\n")
    sys.exit(0)
else:
    print(f"\n  ✘  FAILED — expected ≥{args.min_readings} readings, got {len(readings_hcsr)}")
    if not got_boot:
        print("     Boot message never received — wrong port or firmware not uploaded?")
    print()
    sys.exit(1)
