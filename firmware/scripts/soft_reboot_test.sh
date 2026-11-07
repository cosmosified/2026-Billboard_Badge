#!/bin/sh
# Like boot_test.sh, but restarts the badge with Ctrl-C + Ctrl-D (a soft reboot,
# what Thonny does) instead of a hard reset, then logs the splash refresh.
# Usage (from firmware/): sh scripts/soft_reboot_test.sh [seconds]
SECS="${1:-90}"
PORT="${PORT:-$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)}"
MP="uv run mpremote"
printf '{"load_counter": 0}' > /tmp/panel_config.json
$MP cp /tmp/panel_config.json :/data/panel_config.json >/dev/null
uv run python - "$PORT" "$SECS" <<'EOF'
import sys, time, serial
port, secs = sys.argv[1], float(sys.argv[2])
s = serial.Serial(port, 115200, timeout=0.5)
s.write(b"\x03\x03")
time.sleep(0.5)
s.write(b"\x02")  # leave raw REPL if mpremote left it there
time.sleep(0.3)
s.reset_input_buffer()
s.write(b"\x04")  # soft reboot -> boot.py, main.py
t0 = time.time()
end = t0 + secs
line = b""
while time.time() < end:
    try:
        chunk = s.read(256)
    except Exception as e:
        print(f"[{time.time()-t0:5.1f}s] serial dropped: {e}")
        break
    for b in chunk:
        if b == 10:
            print(f"[{time.time()-t0:5.1f}s] {line.decode(errors='replace').rstrip()}")
            line = b""
        else:
            line += bytes([b])
EOF
