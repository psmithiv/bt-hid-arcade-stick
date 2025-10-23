"""USB HID mirroring helper for tethered debugging.

Allows mirroring BLE HID reports over USB when the device is tethered,
providing an additional debugging and testing path while developing.
"""

from firmware_logging import get_logger


class USBHIDManager:
    """Stub USB HID manager used for state tracking."""

    def __init__(self, enabled=True):
        """
        Initialize the USB HID manager.

        :param bool enabled: Whether USB mirroring is active.
        """
        self._enabled = enabled
        self._last_report = None
        self._logger = get_logger("usb_hid_manager")
        self._logger.debug("USB HID manager initialized; enabled=%s.", self._enabled)

    @property
    def enabled(self):
        """
        Return True when USB HID reporting is active.

        :returns: ``True`` if USB mirroring is enabled.
        :rtype: bool
        """
        return self._enabled

    def set_enabled(self, enabled):
        """
        Update USB HID enabled state.

        :param bool enabled: New enabled value.
        """
        self._enabled = enabled
        self._logger.info("USB HID enabled set to %s.", self._enabled)

    def send_report(self, report):
        """
        Send a HID report over USB if enabled.

        :param dict report: Snapshot of the current button state.
        """
        if not self._enabled:
            self._logger.debug("Skipping USB report; USB HID output disabled.")
            return
        self._last_report = report
        self._logger.debug("USB report recorded: %s.", report)

    @property
    def last_report(self):
        """
        Return the last report dispatched over USB.

        :returns: Stored report dictionary.
        """
        return self._last_report
