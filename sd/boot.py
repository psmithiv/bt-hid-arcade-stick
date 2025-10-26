# CIRCUITPY/boot.py — 16-button gamepad w/ 4 signed axes (X,Y,Z,Rz), Report ID 1
import usb_hid
import binascii
import time

from hid_report import (
    GAMEPAD_INPUT_REPORT_LENGTH,
    GAMEPAD_REPORT_DESCRIPTOR,
    GAMEPAD_REPORT_ID,
)

# Try to make macOS see this as a "new" device by changing product + serial strings.
# Note: VID/PID cannot be changed from CircuitPython boot.py.
def _unique_serial():
    try:
        import microcontroller
        uid = microcontroller.cpu.uid  # bytes
        tail = binascii.hexlify(uid[-4:]).decode().upper()
    except Exception:
        tail = f"{int(time.monotonic())%100000:05d}"
    return f"ARCADE-GP-{tail}-{int(time.monotonic())%10000:04d}"

SERIAL = _unique_serial()
MANUFACTURER = "Plyxal"
PRODUCT = "Arcade Gamepad v2"

# Where available, set human-readable USB identification strings before enabling interfaces.
# These APIs are optional and vary by CircuitPython version; guard them.
try:
    import usb_cdc
    if hasattr(usb_cdc, "set_usb_identification"):
        usb_cdc.set_usb_identification(
            manufacturer=MANUFACTURER,
            product=PRODUCT,
            serial_number=SERIAL,
        )
except Exception:
    pass

try:
    import usb_midi
    if hasattr(usb_midi, "set_usb_identification"):
        usb_midi.set_usb_identification(
            manufacturer=MANUFACTURER,
            product=PRODUCT,
            serial_number=SERIAL,
        )
except Exception:
    pass

gamepad_device = usb_hid.Device(
    report_descriptor=GAMEPAD_REPORT_DESCRIPTOR,
    usage_page=0x01,            # Generic Desktop Controls
    usage=0x05,                 # Game Pad
    report_ids=(GAMEPAD_REPORT_ID,),
    in_report_lengths=(GAMEPAD_INPUT_REPORT_LENGTH,),
    out_report_lengths=(0,),    # no output report
)

# Enable ONLY the gamepad so macOS doesn't see any keyboard/mouse boot interfaces.
usb_hid.enable((gamepad_device,))
