"""
USB HID manager for the Bluetooth HID arcade stick.
Allows mirroring BLE HID reports over USB when the device is tethered,
providing an additional debugging and testing path.
"""

from firmware_logging import get_logger


class USBHIDManager:
    """Stub USB HID manager used for state tracking."""

    def __init__(self, enabled=True):
        self._enabled = enabled
        self._last_report = None
        self._logger = get_logger("usb_hid_manager")
        self._logger.debug("USB HID manager initialized; enabled=%s.", self._enabled)

    @property
    def enabled(self):
        """Return True when USB HID reporting is active."""
        return self._enabled

    def set_enabled(self, enabled):
        """Update USB HID enabled state."""
        self._enabled = enabled
        self._logger.info("USB HID enabled set to %s.", self._enabled)

    def send_report(self, report):
        """Send a HID report over USB if enabled."""
        if not self._enabled:
            self._logger.debug("Skipping USB report; USB HID output disabled.")
            return
        self._last_report = report
        self._logger.debug("USB report recorded: %s.", report)

    @property
    def last_report(self):
        """Return the last report dispatched over USB."""
        return self._last_report
