"""Central configuration for the Bluetooth HID arcade stick firmware.

This module centralizes hardware mappings and tunables so they can be adjusted
without touching the runtime logic.

All buttons are assumed to be wired **active-low** with pull-up resistors.
Update :data:`PIN_MAP` with the exact GPIO connections used on the target PCB
so the firmware reports the correct button state in hardware and when mirrored
through the debug interface.
"""

from firmware_logging import DEBUG

# Logical button order for the HID descriptor (16 straight buttons).
# Prioritize the primary face + shoulder buttons in usages 1-8, place system
# buttons immediately after, and keep the D-pad directions in 13-16. The D-pad
# will also drive the hat switch and X/Y axes so Steam/macOS detect a modern pad.
HID_BUTTONS = [
    "A",
    "B",
    "X",
    "Y",
    "L1",
    "R1",
    "L2",
    "R2",
    "START",
    "SELECT",
    "HOME",
    "PAIRING",  # Reserved / virtual-only slot to keep the descriptor at 16 buttons.
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
]

# Convenience aliases for the D-pad when translating into hat/axes.
DPAD_DEFAULTS = {
    "up": "UP",
    "down": "DOWN",
    "left": "LEFT",
    "right": "RIGHT",
    "axis_min": -127,
    "axis_max": 127,
    "hat_neutral": 0x00,
}

# InputManager polls every entry here (buttons only; virtual buttons ignored when unmapped).
INPUT_BUTTONS = list(HID_BUTTONS)

# GPIO mapping placeholder. Update these entries with the actual board pins.
# Example: "UP": "D5"  (strings are resolved via the board module)
PIN_MAP = {
    "UP": "D5",
    "DOWN": "D6",
    "LEFT": "D9",
    "RIGHT": "D10",
    "A": "D11",
    "B": "D12",
    "X": "D13",  # On-board LED pin; suitable for quick testing
    "Y": "D0",
    "L1": "D1",
    "R1": "D4",
    "L2": "A0",
    "R2": "A1",
    "START": "A2",
    "SELECT": "A3",
    "HOME": "A4",
    # Pairing button is virtual-only by default; mapped to None while wiring is pending.
    "PAIRING": None,
}

# Dedicated pairing button pin (set to a board pin when wired).
PAIRING_BUTTON_PIN = None

# Debounce interval in milliseconds for button state stabilization.
DEBOUNCE_MS = 10

# Duration the pairing button must be held (ms) to trigger pairing.
PAIRING_HOLD_MS = 3000

# Time to remain in explicit pairing mode before timing out (seconds).
PAIRING_TIMEOUT_SEC = 180

# BLE advertising name exposed to hosts.
BLE_DEVICE_NAME = "Paul ArcadeStick"

# Flag controlling whether USB HID mirroring is active.
USB_HID_ENABLED = True

# HID report configuration (placeholder for future expansion).
HID_SETTINGS = {
    "device_name": BLE_DEVICE_NAME,
    "usb_enabled": USB_HID_ENABLED,
}

# Debug configuration options.
DEBUG_SETTINGS = {
    "enabled": True,
    "state_broadcast": True,
    "virtual_buttons": ["PAIRING"],
}

# BLE configuration options.
BLE_SETTINGS = {
    "device_name": BLE_DEVICE_NAME,
    "pairing_hold_ms": PAIRING_HOLD_MS,
    "pairing_timeout_sec": PAIRING_TIMEOUT_SEC,
    "pairing_button_pin": PAIRING_BUTTON_PIN,
}

LOG_LEVEL = DEBUG

CONTROLLER_CONFIG = {
    "buttons": INPUT_BUTTONS,
    "hid_buttons": HID_BUTTONS,
    "dpad_up": DPAD_DEFAULTS["up"],
    "dpad_down": DPAD_DEFAULTS["down"],
    "dpad_left": DPAD_DEFAULTS["left"],
    "dpad_right": DPAD_DEFAULTS["right"],
    "axis_min": DPAD_DEFAULTS["axis_min"],
    "axis_max": DPAD_DEFAULTS["axis_max"],
    "hat_neutral": DPAD_DEFAULTS["hat_neutral"],
    "pin_map": PIN_MAP,
    "debounce_ms": DEBOUNCE_MS,
    "hid": HID_SETTINGS,
    "ble": BLE_SETTINGS,
    "power": {},
    "debug": DEBUG_SETTINGS,
    "log_level": LOG_LEVEL,
}
