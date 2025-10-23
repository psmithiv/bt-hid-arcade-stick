"""
BLE management layer for the Bluetooth HID arcade stick.
Handles advertising, connection lifecycle, pairing control, and exposes
the HID service used by the HID controller.
"""

import time

from firmware_logging import get_logger

try:
    from adafruit_ble import BLERadio
    from adafruit_ble.advertising.standard import ProvideServicesAdvertisement
    from adafruit_ble.advertising import AdvertisementError
    from adafruit_ble.services.standard.hid import HIDService
except ImportError:  # pragma: no cover - host environment / unit tests
    BLERadio = None
    ProvideServicesAdvertisement = None
    AdvertisementError = RuntimeError
    HIDService = None

try:
    import digitalio
except ImportError:  # pragma: no cover - host environment / unit tests
    digitalio = None


class BLEManager:
    """Manage BLE HID lifecycle, pairing, and connection state."""

    def __init__(self, config):
        """
        Build the BLE manager around the provided configuration.

        :param dict config: BLE configuration block from :mod:`config`, including
            the advertised name, pairing timeouts, and optional pairing button pin.
        """
        self._logger = get_logger("ble_manager")
        self._config = config or {}
        self._device_name = self._config.get("device_name", "ArcadeStick")
        self._pairing_hold_ms = self._config.get("pairing_hold_ms", 3000)
        self._pairing_timeout_sec = self._config.get("pairing_timeout_sec", 180)
        self._pair_button_pin = self._config.get("pairing_button_pin")

        self._ble = None
        self._hid_service = None
        self._advertisement = None

        self._connected = False
        self._pairing_active = False
        self._pairing_start = None
        self._pair_press_start = None
        self._bonded = False

        self._pair_button = self._setup_pair_button()
        self._event_listeners = []

        if BLERadio is None or HIDService is None:
            self._logger.warning("BLE stack is unavailable; disabling Bluetooth functionality.")
            self._emit_event(
                "disabled",
                message="BLE stack unavailable on this platform",
                reason="adafruit_ble_missing",
            )
            return

        self._initialize_ble()
        self._bonded = self._detect_existing_bond()

        if self._bonded:
            self._logger.info("Existing bond detected; advertising for reconnection.")
            self._start_advertising(initial=True)
        else:
            self._logger.info("No bond detected; entering automatic pairing mode.")
            self.enter_pairing_mode()

    # ---------------------------------------------------------------------
    # Event listener support

    def add_event_listener(self, listener):
        """
        Register a callable notified when BLE state changes.

        :param callable listener: Function accepting a single dictionary payload
            describing the BLE event.
        """
        if listener in self._event_listeners:
            return
        self._event_listeners.append(listener)
        try:
            listener(self._status_snapshot())
        except Exception:  # pragma: no cover - listener safety
            pass

    def remove_event_listener(self, listener):
        """
        Remove a previously registered event listener.

        :param callable listener: Listener previously passed to :meth:`add_event_listener`.
        """
        if listener in self._event_listeners:
            self._event_listeners.remove(listener)

    def _emit_event(self, event, **payload):
        """Dispatch a BLE status event to registered listeners."""
        if not self._event_listeners:
            return
        data = {"event": event, "timestamp": time.monotonic()}
        for k, v in payload.items():
            data[k] = v
        for listener in list(self._event_listeners):
            try:
                listener(data)
            except Exception:  # pragma: no cover - listener safety
                pass

    def _status_snapshot(self):
        """Create a snapshot describing the current BLE status."""
        advertising = False
        if self._ble is not None:
            try:
                advertising = bool(self._ble.advertising)
            except AttributeError:
                advertising = False

        message = "BLE status"
        if self._ble is None:
            message = "BLE stack unavailable"
        elif self._connected:
            message = "BLE connected"
        elif self._pairing_active:
            message = "BLE pairing active"
        elif advertising:
            message = "BLE advertising"

        return {
            "event": "status",
            "message": message,
            "connected": self._connected,
            "pairing_active": self._pairing_active,
            "bonded": self._bonded,
            "advertising": advertising,
            "timestamp": time.monotonic(),
        }

    def _setup_pair_button(self):
        """Configure the pairing button input if hardware is assigned."""
        if self._pair_button_pin is None:
            self._logger.debug("Pairing button pin is not configured; skipping hardware setup.")
            return None
        if digitalio is None:
            self._logger.warning("digitalio module is unavailable; pairing button support disabled.")
            return None

        button = digitalio.DigitalInOut(self._pair_button_pin)
        button.switch_to_input(pull=digitalio.Pull.UP)
        self._logger.info("Pairing button configured on pin %s.", self._pair_button_pin)
        return button

    def _initialize_ble(self):
        """Instantiate BLE radio, HID service, and advertisement."""
        self._hid_service = HIDService()
        self._ble = BLERadio()
        try:
            self._ble.name = self._device_name
        except AttributeError:
            pass  # Some adapters may not allow renaming.
        self._advertisement = ProvideServicesAdvertisement(self._hid_service)
        self._advertisement.complete_name = self._device_name
        self._logger.info("Initialized BLE stack with advertised name %s.", self._device_name)
        self._emit_event(
            "initialized",
            message=f"BLE initialized as '{self._device_name}'",
            device_name=self._device_name,
        )

    def _detect_existing_bond(self):
        """Determine whether the adapter already has bonded peers."""
        if self._ble is None:
            return False
        try:
            bonded = getattr(self._ble._adapter, "bonded", None)  # pylint: disable=protected-access
            has_bond = bool(bonded)
            self._logger.debug("Detected bonded peers: %s.", bonded)
            return has_bond
        except AttributeError:
            self._logger.debug("Adapter does not expose bonded peers.")
            return False

    @property
    def hid_service(self):
        """
        Expose the HID service for consumption by other modules.

        :returns: :class:`adafruit_ble.services.standard.hid.HIDService` instance or ``None``.
        """
        return self._hid_service

    @property
    def connected(self):
        """
        Return the current BLE connection status.

        :returns: ``True`` if at least one Central is connected.
        :rtype: bool
        """
        return self._connected

    def poll(self):
        """
        Service BLE events such as advertising, connection, or pairing.
        This should be called frequently from the main loop.

        :returns: ``None``
        """
        if self._ble is None:
            return

        now = time.monotonic()
        self._update_pair_button(now)
        self._update_connection_state()
        self._enforce_pairing_timeout(now)

    def _update_pair_button(self, now):
        """Monitor the pairing button for long-press detection."""
        if self._pair_button is None:
            return

        pressed = not self._pair_button.value  # Active-low assumption

        if pressed and self._pair_press_start is None:
            self._pair_press_start = now
            self._logger.debug("Pairing button press detected.")

        if pressed and self._pair_press_start is not None:
            held_ms = (now - self._pair_press_start) * 1000
            if held_ms >= self._pairing_hold_ms and not self._pairing_active:
                self._logger.info("Pairing button held for %.0f ms; entering pairing mode.", held_ms)
                self.enter_pairing_mode()

        if not pressed and self._pair_press_start is not None:
            self._logger.debug(
                "Pairing button released after %.0f ms.", (now - self._pair_press_start) * 1000
            )
            self._pair_press_start = None

    def _update_connection_state(self):
        """Monitor BLE connection transitions and manage advertising."""
        if self._ble is None:
            return

        if self._ble.connected:
            if not self._connected:
                self._connected = True
                self._bonded = True
                self._pairing_active = False
                self._pairing_start = None
                self._logger.info("BLE connection established; active connections: %d.", len(self._ble.connections))
                try:
                    self._ble.stop_advertising()
                except AdvertisementError:
                    pass
                self._emit_event(
                    "connected",
                    message="BLE connected",
                    connections=len(self._ble.connections),
                )
                self._emit_event(
                    "pairing_active",
                    message="Pairing mode deactivated (connected)",
                    active=False,
                )
            return

        if self._connected:
            self._logger.info("BLE connection closed.")
            self._connected = False
            self._emit_event("disconnected", message="BLE disconnected")

        if not self._ble.advertising:
            self._start_advertising()

    def _enforce_pairing_timeout(self, now):
        """Exit pairing mode if the timeout expires without connection."""
        if not self._pairing_active or self._pairing_start is None:
            return

        if (now - self._pairing_start) >= self._pairing_timeout_sec:
            self._logger.info("Pairing mode timed out after %d seconds.", self._pairing_timeout_sec)
            self._pairing_active = False
            self._pairing_start = None
            self._emit_event(
                "pairing_timeout",
                message=f"Pairing mode timed out after {self._pairing_timeout_sec}s",
                timeout=self._pairing_timeout_sec,
            )
            self._emit_event(
                "pairing_active",
                message="Pairing mode deactivated (timeout)",
                active=False,
            )
            self._start_advertising()

    def _start_advertising(self, initial=False):
        """Begin BLE advertising if possible."""
        if self._ble is None or self._advertisement is None:
            return

        if self._pairing_active:
            self._logger.info("Advertising in pairing mode under identifier '%s'.", self._device_name)
            advert_mode = "pairing"
        elif initial and not self._bonded:
            self._logger.info("No existing bond detected; advertising for new connection.")
            advert_mode = "initial"
        else:
            self._logger.debug("Advertising for reconnection as '%s'.", self._device_name)
            advert_mode = "reconnect"

        try:
            self._ble.start_advertising(self._advertisement)
            self._emit_event(
                "advertising",
                message=f"Advertising ({advert_mode})",
                mode=advert_mode,
            )
        except AdvertisementError as exc:
            self._logger.error("Encountered advertising error: %s.", exc)
            self._emit_event(
                "advertising_error",
                message=f"Advertising error: {exc}",
                error=str(exc),
            )

    def enter_pairing_mode(self):
        """
        Clear existing bonds (if any) and start pairing mode advertising.

        :returns: ``None``
        """
        if self._ble is None:
            self._logger.warning("BLE stack is unavailable; pairing mode request ignored.")
            self._emit_event(
                "pairing_error",
                message="Cannot enter pairing mode; BLE stack unavailable",
                reason="ble_unavailable",
            )
            return

        self._logger.info("Entering pairing mode; clearing bonds and restarting advertising.")
        self._pairing_active = True
        self._pairing_start = time.monotonic()
        self._bonded = False
        self._emit_event(
            "pairing_active",
            message="Pairing mode activated",
            active=True,
        )

        try:
            self._ble.stop_advertising()
        except AdvertisementError:
            pass

        self._ble.disconnect_all()
        try:
            self._ble.erase_bonding()
        except AttributeError:
            self._logger.debug("erase_bonding operation not exposed on this adapter.")

        self._start_advertising()
