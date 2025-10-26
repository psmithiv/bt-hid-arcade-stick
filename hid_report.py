"""Shared HID report descriptor definitions.

The descriptor matches the USB boot-time configuration in ``sd/boot.py`` and is
also reused for the BLE HID service so both transports expose the same 16-button
gamepad layout with four signed axes (X, Y, Z, Rz).
"""

# Report ID used by both USB and BLE transports.
GAMEPAD_REPORT_ID = 0x01

# HID report descriptor: 16 buttons + 4 axes (signed 8-bit).
GAMEPAD_REPORT_DESCRIPTOR = bytes(
    (
        0x05,
        0x01,  # Usage Page (Generic Desktop)
        0x09,
        0x05,  # Usage (Game Pad)
        0xA1,
        0x01,  # Collection (Application)
        0x85,
        GAMEPAD_REPORT_ID,  #   Report ID (1)
        # 16 buttons: 2 bytes
        0x05,
        0x09,  #   Usage Page (Button)
        0x19,
        0x01,  #   Usage Minimum (1)
        0x29,
        0x10,  #   Usage Maximum (16)
        0x15,
        0x00,  #   Logical Min (0)
        0x25,
        0x01,  #   Logical Max (1)
        0x95,
        0x10,  #   Report Count (16)
        0x75,
        0x01,  #   Report Size (1)
        0x81,
        0x02,  #   Input (Data, Var, Abs)
        # 4 axes: X, Y, Z, Rz — each signed 8-bit (-127..127)
        0x05,
        0x01,  #   Usage Page (Generic Desktop)
        0x09,
        0x30,  #   Usage (X)
        0x09,
        0x31,  #   Usage (Y)
        0x09,
        0x32,  #   Usage (Z)
        0x09,
        0x35,  #   Usage (Rz)
        0x15,
        0x81,  #   Logical Min (-127)
        0x25,
        0x7F,  #   Logical Max (127)
        0x75,
        0x08,  #   Report Size (8)
        0x95,
        0x04,  #   Report Count (4)
        0x81,
        0x02,  #   Input (Data, Var, Abs)
        0xC0,  # End Collection
    )
)

# Length of the full HID input report (report ID + payload).
GAMEPAD_INPUT_REPORT_LENGTH = 1 + 2 + 4  # 1 ID + 2 button bytes + 4 axis bytes
