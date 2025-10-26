# CIRCUITPY/boot.py — 16-button gamepad w/ 4 signed axes (X,Y,Z,Rz), Report ID 1
import usb_hid
import binascii
import time

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
try:controller
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

# HID report descriptor: 16 buttons + 4 axes (signed 8-bit)
GAMEPAD_REPORT_DESCRIPTOR = bytes((
    0x05, 0x01,       # Usage Page (Generic Desktop)
    0x09, 0x05,       # Usage (Game Pad)
    0xA1, 0x01,       # Collection (Application)
    0x85, 0x01,       #   Report ID (1)

    # 16 buttons: 2 bytes
    0x05, 0x09,       #   Usage Page (Button)
    0x19, 0x01,       #   Usage Minimum (1)
    0x29, 0x10,       #   Usage Maximum (16)
    0x15, 0x00,       #   Logical Min (0)
    0x25, 0x01,       #   Logical Max (1)
    0x95, 0x10,       #   Report Count (16)
    0x75, 0x01,       #   Report Size (1)
    0x81, 0x02,       #   Input (Data, Var, Abs)

    # 4 axes: X, Y, Z, Rz — each signed 8-bit (-127..127)
    0x05, 0x01,       #   Usage Page (Generic Desktop)
    0x09, 0x30,       #   Usage (X)
    0x09, 0x31,       #   Usage (Y)
    0x09, 0x32,       #   Usage (Z)
    0x09, 0x35,       #   Usage (Rz)
    0x15, 0x81,       #   Logical Min (-127)
    0x25, 0x7F,       #   Logical Max (127)
    0x75, 0x08,       #   Report Size (8)
    0x95, 0x04,       #   Report Count (4)
    0x81, 0x02,       #   Input (Data, Var, Abs)
    0xC0,             # End Collection
))

gamepad_device = usb_hid.Device(
    report_descriptor=GAMEPAD_REPORT_DESCRIPTOR,
    usage_page=0x01,            # Generic Desktop Controls
    usage=0x05,                 # Game Pad
    report_ids=(1,),
    in_report_lengths=(7,),     # 1-byte ID + 6-byte payload
    out_report_lengths=(0,),    # no output report
)

# Enable ONLY the gamepad so macOS doesn't see any keyboard/mouse boot interfaces.
usb_hid.enable((gamepad_device,))