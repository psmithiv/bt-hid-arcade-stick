"""
Configuration constants for the Bluetooth HID arcade stick firmware.
This module centralizes hardware mappings and tunables so they can be
adjusted without touching the runtime logic.
"""

from firmware_logging import DEBUG

# Logical button order for the controller; handshake with HID descriptor.
BUTTONS = [
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
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
]

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
    "PAIRING": "A5",
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
    "buttons": BUTTONS,
    "pin_map": PIN_MAP,
    "debounce_ms": DEBOUNCE_MS,
    "hid": HID_SETTINGS,
    "ble": BLE_SETTINGS,
    "power": {},
    "debug": DEBUG_SETTINGS,
    "log_level": LOG_LEVEL,
}
