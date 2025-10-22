"""
Entry point for the Bluetooth HID arcade stick firmware.
Initializes subsystems and enters the main service loop.
"""

import time

from config import CONTROLLER_CONFIG
from ble_manager import BLEManager
from usb_hid_manager import USBHIDManager
from input_manager import InputManager
from hid_controller import HIDController
from power_manager import PowerManager
from debug_interface import DebugInterface
from firmware_logging import get_logger, set_level

logger = get_logger("code")

def main():
    """Firmware entry point."""
    set_level(CONTROLLER_CONFIG.get("log_level"))
    logger.info("Starting Bluetooth HID arcade stick firmware initialization sequence.")

    ble_manager = BLEManager(CONTROLLER_CONFIG.get("ble", {}))
    usb_config = CONTROLLER_CONFIG.get("hid", {})
    usb_manager = USBHIDManager(enabled=usb_config.get("usb_enabled", True))
    input_manager = InputManager(CONTROLLER_CONFIG)
    hid_controller = HIDController(ble_manager, usb_manager, CONTROLLER_CONFIG)
    power_manager = PowerManager(CONTROLLER_CONFIG.get("power", {}))
    debug_interface = DebugInterface(
        hid_controller,
        ble_manager=ble_manager,
        config=CONTROLLER_CONFIG.get("debug", {}),
    )

    logger.info("Firmware initialization completed; entering main service loop.")

    while True:  # Main service loop (will run indefinitely on-device)
        ble_manager.poll()
        power_manager.poll()
        debug_interface.poll()
        events = input_manager.poll()
        if events.pressed or events.released:
            hid_controller.process_inputs(events)
        time.sleep(0.01)


if __name__ == "__main__":
    main()
