"""
Serial debug interface enabling virtual button injection and state
inspection from a host development workstation.
"""

import json
import time

from input_manager import InputEvents
from firmware_logging import get_logger

try:
    import supervisor
except ImportError:  # pragma: no cover - host environment
    supervisor = None

try:
    import sys
except ImportError:  # pragma: no cover - unlikely
    sys = None


class DebugInterface:
    """Facilitates host-driven debugging over the USB serial console."""

    def __init__(self, hid_controller, ble_manager=None, config=None):
        self._logger = get_logger("debug_interface")
        self._hid = hid_controller
        self._ble_manager = ble_manager
        self._config = config or {}
        self._enabled = self._config.get("enabled", False)
        self._broadcast_state = self._config.get("state_broadcast", True)
        self._virtual_pressed = set()
        self._last_state_signature = None
        self._valid_buttons = set(self._hid.button_names)
        self._serial_connected = False

        if not self._enabled:
            self._logger.info("Debug interface disabled by configuration.")
            return

        if supervisor is None or sys is None:
            self._enabled = False
            self._logger.warning("Supervisor or sys modules are unavailable; disabling debug interface.")
            return

        if self._broadcast_state:
            self._hid.set_state_callback(self.publish_state)

        self._register_ble_listener()
        self._announce_ready()

    def poll(self):
        """Process inbound serial commands and manage periodic state reports."""
        if not self._enabled or supervisor is None or sys is None:
            return

        connected = supervisor.runtime.serial_connected
        if connected != self._serial_connected:
            self._serial_connected = connected
            status = "connected" if connected else "disconnected"
            self._send_message("INFO", {"message": f"Serial {status}"})

        if connected:
            self._read_commands()

    def publish_state(self, buttons):
        """Emit the current controller state to the host debugger."""
        if not self._broadcast_state:
            return
        payload = {
            "buttons": buttons,
            "virtual": sorted(self._virtual_pressed),
            "timestamp": time.monotonic(),
        }
        signature = (tuple(payload["buttons"]), tuple(payload["virtual"]))
        if signature == self._last_state_signature:
            return
        self._last_state_signature = signature
        self._send_message("STATE", payload)

    def _read_commands(self):
        """Consume available serial commands."""
        while supervisor.runtime.serial_bytes_available:
            line = sys.stdin.readline().strip()
            if not line:
                continue
            self._handle_command(line)

    def _handle_command(self, line):
        """Parse and execute a single command line."""
        parts = line.split()
        if not parts:
            return

        command = parts[0].upper()
        args = parts[1:]

        if command == "PRESS" and args:
            self._virtual_press(args[0])
        elif command == "RELEASE" and args:
            self._virtual_release(args[0])
        elif command == "STATE?":
            self.publish_state(sorted(self._hid.active_buttons))
        elif command == "PAIR":
            self._trigger_pairing()
        elif command == "LOG" and len(args) >= 2:
            self._handle_host_log(args)
        elif command == "HELP":
            self._send_help()
        else:
            self._send_message("ERR", {"command": line})

    def _virtual_press(self, button_name):
        """Simulate a button press."""
        name = button_name.upper()
        if name not in self._valid_buttons:
            self._send_message("ERR", {"message": f"Unknown button: {name}"})
            return
        self._logger.info("Host requested virtual press: %s", name)
        self._virtual_pressed.add(name)
        self._hid.process_inputs(InputEvents(pressed={name}, released=set()))

    def _virtual_release(self, button_name):
        """Simulate a button release."""
        name = button_name.upper()
        if name not in self._valid_buttons:
            self._send_message("ERR", {"message": f"Unknown button: {name}"})
            return
        self._logger.info("Host requested virtual release: %s", name)
        if name in self._virtual_pressed:
            self._virtual_pressed.remove(name)
        self._hid.process_inputs(InputEvents(pressed=set(), released={name}))

    def _trigger_pairing(self):
        """Invoke BLE pairing mode from the host."""
        if self._ble_manager is None:
            self._send_message("WARN", {"message": "BLE manager unavailable"})
            return
        self._ble_manager.enter_pairing_mode()
        self._send_message("INFO", {"message": "Pairing mode requested"})

    def _handle_host_log(self, args):
        """Log a message forwarded by the host UI."""
        level = args[0]
        logger_name = args[1]
        message = " ".join(args[2:]) if len(args) > 2 else ""
        message = message.replace("\\n", "\n")
        try:
            target_logger = get_logger(logger_name)
            target_logger.log(level, message)
        except Exception as exc:  # pragma: no cover - defensive
            self._send_message("ERR", {"message": f"LOG failed: {exc}"})

    def _send_help(self):
        """Publish available commands."""
        help_text = {
            "commands": [
                "PRESS <BUTTON>",
                "RELEASE <BUTTON>",
                "STATE?",
                "PAIR",
                "LOG <LEVEL> <LOGGER> <MESSAGE>",
                "HELP",
            ],
            "buttons": self._hid.button_names,
        }
        self._send_message("HELP", help_text)

    def _announce_ready(self):
        """Notify host tools that the interface is active."""
        self._send_message("READY", {"buttons": self._hid.button_names})

    @staticmethod
    def _send_message(label, payload):
        """Send a JSON-formatted debug message to the serial console."""
        data = dict(payload or {})
        data.setdefault("type", label.lower())
        data.setdefault("timestamp", time.monotonic())
        serialized = json.dumps(data)
        try:
            print(serialized)
        except OSError as exc:
            if not DebugInterface._is_transport_flush_error(exc):
                raise
            DebugInterface._raw_write(serialized)
        DebugInterface._try_flush()

    @staticmethod
    def _is_transport_flush_error(exc):
        """Return True if the exception matches the USB CDC flush bug."""
        return bool(exc.args) and exc.args[0] == 22

    @staticmethod
    def _raw_write(serialized):
        """Fallback write that bypasses print()-triggered flush behaviour."""
        if sys is None:
            return
        try:
            sys.stdout.write(serialized + "\n")
        except OSError:
            # Ignore downstream transport errors to keep firmware running.
            pass

    @staticmethod
    def _try_flush():
        """Best-effort flush that tolerates transports without flush support."""
        if sys is None:
            return
        try:
            sys.stdout.flush()
        except (AttributeError, OSError):
            pass


    def _register_ble_listener(self):
        """Forward BLE lifecycle events to the debug console."""
        if self._ble_manager is None:
            return
        add_listener = getattr(self._ble_manager, "add_event_listener", None)
        if add_listener is None:
            return
        add_listener(self._handle_ble_event)

    def _handle_ble_event(self, event):
        """Publish BLE status updates in a human-friendly format."""
        label = event.get("event", "unknown")
        message = event.get("message") or f"BLE event: {label}"
        details = []
        for key, value in event.items():
            if key in {"event", "message", "timestamp"}:
                continue
            details.append(f"{key}={value}")
        if details:
            message = f"{message} [{', '.join(details)}]"

        payload = {
            "message": message,
            "source": "BLE",
            "event": label,
        }
        if "timestamp" in event:
            payload["timestamp"] = event["timestamp"]

        self._send_message("INFO", payload)
