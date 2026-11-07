#!/bin/sh
# Hard-reset the badge so it shows the boot splash, and log the serial output.
# Writes {"load_counter": 0} to /data/panel_config.json on the badge so the
# splash shows. A real full refresh prints ~33 s after "display working"; one
# that "finishes" in a second or two means the panel never ran its waveform.
# Usage (from firmware/): sh scripts/boot_test.sh [seconds]
SECS="${1:-90}"
PORT="${PORT:-$(ls /dev/cu.usbmodem* 2>/dev/null | head -1)}"
if [ -z "$PORT" ]; then
    echo "No badge serial port (/dev/cu.usbmodem*). Plug in the badge or set PORT." >&2
    exit 1
fi
MP="uv run mpremote"
printf '{"load_counter": 0}' > /tmp/panel_config.json
$MP cp /tmp/panel_config.json :/data/panel_config.json >/dev/null
$MP reset >/dev/null 2>&1
sleep 1
uv run python - "$PORT" "$SECS" <<'EOF'
import sys, time, serial
port, secs = sys.argv[1], float(sys.argv[2])
end = time.time() + secs
s = None
while s is None and time.time() < end:
    try:
        s = serial.Serial(port, 115200, timeout=0.5)
    except serial.SerialException:
        time.sleep(0.2)
if s is None:
    sys.exit(f"could not open {port}")
t0 = time.time()
line = b""
while time.time() < end:
    try:
        chunk = s.read(256)
    except serial.SerialException as e:
        print(f"[{time.time()-t0:5.1f}s] serial dropped: {e}")
        break
    for b in chunk:
        if b == 10:
            print(f"[{time.time()-t0:5.1f}s] {line.decode(errors='replace').rstrip()}")
            line = b""
        else:
            line += bytes([b])
EOF
