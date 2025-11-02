"""Shared HID report descriptor definitions for the arcade stick.

The updated layout advertises a modern gamepad profile that matches the
expectations of Steam and mainstream operating systems (macOS, Windows,
Linux) when a generic arcade stick is attached. Highlights:

- 16 digital buttons (includes the D-pad so legacy hosts still see them).
- Dedicated hat switch for the D-pad to align with contemporary gamepads.
- Signed X/Y axes that mirror the D-pad directions (left/right, up/down).

Report layout (with Report ID):
[0] : Report ID (0x01)
[1] : Buttons 1‒8   (bitfield)
[2] : Buttons 9‒16  (bitfield)
[3] : Hat switch (low nibble, 0 = neutral, 1‒8 = compass directions) + padding nibble (set to 0xF)
[4] : X axis (signed 8-bit, -127 = left, 127 = right)
[5] : Y axis (signed 8-bit, -127 = up,   127 = down)

Total length = 1 (ID) + 5 (payload) = 6 bytes.
"""

# Report ID used by both USB and BLE transports.
GAMEPAD_REPORT_ID = 0x01

# HID report descriptor: 16 buttons, hat switch, and X/Y axes.
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
        0x05,
        0x09,  #   Usage Page (Button)
        0x19,
        0x01,  #   Usage Minimum (1)
        0x29,
        0x10,  #   Usage Maximum (16)
        0x15,
        0x00,  #   Logical Minimum (0)
        0x25,
        0x01,  #   Logical Maximum (1)
        0x95,
        0x10,  #   Report Count (16 buttons)
        0x75,
        0x01,  #   Report Size (1 bit)
        0x81,
        0x02,  #   Input (Data,Var,Abs)
        0x05,
        0x01,  #   Usage Page (Generic Desktop)
        0x09,
        0x39,  #   Usage (Hat switch)
        0x15,
        0x01,  #   Logical Minimum (1)
        0x25,
        0x08,  #   Logical Maximum (8)
        0x75,
        0x04,  #   Report Size (4 bits)
        0x95,
        0x01,  #   Report Count (1 hat)
        0x81,
        0x42,  #   Input (Data,Var,Abs,Null state)
        0x75,
        0x04,  #   Report Size (4 bits)
        0x95,
        0x01,  #   Report Count (1 pad nibble)
        0x81,
        0x01,  #   Input (Const,Array,Abs) – padding nibble
        0x09,
        0x30,  #   Usage (X)
        0x09,
        0x31,  #   Usage (Y)
        0x15,
        0x81,  #   Logical Minimum (-127)
        0x25,
        0x7F,  #   Logical Maximum (127)
        0x75,
        0x08,  #   Report Size (8 bits)
        0x95,
        0x02,  #   Report Count (2 axes)
        0x81,
        0x02,  #   Input (Data,Var,Abs)
        0xC0,  # End Collection
    )
)

# Length of the full HID input report (Report ID + payload).
GAMEPAD_INPUT_REPORT_LENGTH = 1 + 5  # = 6 bytes
