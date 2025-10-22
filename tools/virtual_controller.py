#!/usr/bin/env python3
"""
Interactive desktop debugger UI for the Bluetooth HID arcade stick.
Provides a quick way to send button events to the firmware debug
interface and to view structured log output over the USB serial link.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence

from PySide6.QtCore import Q_ARG, QObject, QThread, Qt, QMetaObject, Signal, Slot
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QMainWindow,
    QStyle,
    QToolButton,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QTextCursor, QTextDocument

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from firmware_logging import INFO, get_level_by_name, get_logger

try:  # pyserial is required for host <-> device communication.
    import serial  # type: ignore
    from serial.tools import list_ports  # type: ignore
except ImportError:  # pragma: no cover - runtime dependency check
    serial = None  # type: ignore
    list_ports = None  # type: ignore

SYSTEM_BUTTONS = ["HOME", "START", "SELECT", "PAIRING"]
DEFAULT_BAUDRATE = 115_200
_LEVEL_PRIORITY = {
    "DEBUG": 10,
    "INFO": 20,
    "WARNING": 30,
    "ERROR": 40,
    "CRITICAL": 50,
}


@dataclass
class SerialConfig:
    port: Optional[str]
    baudrate: int = DEFAULT_BAUDRATE
    auto_detect: bool = True


class _SerialWorker(QObject):
    """Background worker that owns the serial connection."""

    line_received = Signal(str)
    connected_changed = Signal(bool)
    error = Signal(str)
    finished = Signal()

    def __init__(self, port: str, baudrate: int):
        super().__init__()
        self._port = port
        self._baudrate = baudrate
        self._serial = None
        self._stop_requested = False

    @Slot()
    def start(self):
        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=0.1)
            self.connected_changed.emit(True)
        except Exception as exc:  # pragma: no cover - hardware interaction
            self.error.emit(f"Failed to open {self._port}: {exc}")
            self.connected_changed.emit(False)
            self.finished.emit()
            return

        try:
            while not self._stop_requested:
                try:
                    line = self._serial.readline()
                except Exception as exc:  # pragma: no cover - hardware interaction
                    self.error.emit(f"Serial read failed: {exc}")
                    break
                if not line:
                    continue
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    self.line_received.emit(decoded)
        finally:
            self.connected_changed.emit(False)
            if self._serial is not None:
                try:
                    self._serial.close()
                except Exception:  # pragma: no cover - best-effort close
                    pass
            self.finished.emit()

    @Slot(str)
    def send(self, text: str):
        if self._serial is None:
            return
        try:
            payload = text if text.endswith("\n") else f"{text}\n"
            self._serial.write(payload.encode("utf-8"))
            self._serial.flush()
        except Exception as exc:  # pragma: no cover - hardware interaction
            self.error.emit(f"Serial write failed: {exc}")

    @Slot()
    def stop(self):
        self._stop_requested = True


class SerialBridge(QObject):
    """Qt-friendly wrapper around the serial worker thread."""

    line_received = Signal(str)
    connection_changed = Signal(bool)
    error = Signal(str)

    def __init__(self, port: str, baudrate: int):
        super().__init__()
        self._thread: Optional[QThread] = QThread()
        self._worker = _SerialWorker(port, baudrate)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.start)
        self._worker.line_received.connect(self.line_received)
        self._worker.connected_changed.connect(self.connection_changed)
        self._worker.error.connect(self.error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.finished.connect(self._handle_worker_finished)
        self._thread.finished.connect(self._handle_thread_finished)

    def start(self):
        if self._thread is not None:
            self._thread.start()

    def stop(self):
        if self._thread is None or self._worker is None:
            return
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "stop", Qt.QueuedConnection)
            self._thread.quit()
            self._thread.wait()
        self._worker = None
        self._thread = None

    def send(self, text: str):
        if self._worker is None:
            return
        QMetaObject.invokeMethod(
            self._worker,
            "send",
            Qt.QueuedConnection,
            Q_ARG(str, text),
        )

    @Slot()
    def _handle_worker_finished(self):
        self._worker = None
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()

    @Slot()
    def _handle_thread_finished(self):
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None


class DebuggerWindow(QMainWindow):
    """Interactive debugger window hooked up to the firmware serial protocol."""

    def __init__(self, serial_config: SerialConfig):
        super().__init__()
        self.setWindowTitle("Arcade Stick Debugger")

        central = QWidget()
        layout = QVBoxLayout()
        central.setLayout(layout)

        self._status_label = QLabel("Status: Disconnected")
        layout.addWidget(self._status_label)

        controls_layout = QHBoxLayout()
        self._button_widgets = {}
        controls_layout.addWidget(self._build_dpad_group(), stretch=1)
        controls_layout.addWidget(self._build_face_group(), stretch=1)
        layout.addLayout(controls_layout)

        layout.addWidget(self._build_system_group())

        self._log_filter = QComboBox()
        self._log_filter.addItems(["ALL", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self._log_filter.setCurrentText("INFO")
        self._log_filter.currentTextChanged.connect(self._handle_log_filter_change)
        self._search_term = ""
        self._search_cursor: Optional[QTextCursor] = None
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search logs")
        self._search_input.textChanged.connect(self._handle_search_text_change)
        self._search_prev_button = QToolButton()
        self._search_prev_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowBack))
        self._search_prev_button.clicked.connect(self._search_previous)
        self._search_next_button = QToolButton()
        self._search_next_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowForward))
        self._search_next_button.clicked.connect(self._search_next)
        self._logger_name = "virtual_controller"

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setPlaceholderText("Waiting for device logs...")
        log_controls = QHBoxLayout()
        log_controls.addWidget(QLabel("Log level:"))
        log_controls.addWidget(self._log_filter)
        log_controls.addStretch()
        log_controls.addWidget(QLabel("Search:"))
        self._search_input.setStyleSheet(
            """
            QLineEdit {
                border-radius: 6px;
                padding: 3px 5px;
            }
            QLineEdit:focus {
                border: 1px solid #666;
                box-shadow: 0 0 6px rgba(80, 80, 80, 0.6);
            }
            """
        )
        log_controls.addWidget(self._search_input)
        button_style = "border-radius: 6px;"
        self._search_prev_button.setFixedHeight(32)
        self._search_prev_button.setStyleSheet(button_style)
        log_controls.addWidget(self._search_prev_button)
        self._search_next_button.setFixedHeight(32)
        self._search_next_button.setStyleSheet(button_style)
        log_controls.addWidget(self._search_next_button)
        save_button = QToolButton()
        save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        save_button.setToolTip("Save log to file")
        save_button.clicked.connect(self._handle_save_logs)
        save_button.setFixedHeight(32)
        save_button.setStyleSheet(button_style)
        log_controls.addWidget(save_button)
        clear_button = QToolButton()
        clear_button.setIcon(self.style().standardIcon(QStyle.SP_DialogResetButton))
        clear_button.setToolTip("Clear log")
        clear_button.clicked.connect(self._handle_clear_logs)
        clear_button.setFixedHeight(32)
        clear_button.setStyleSheet(button_style)
        log_controls.addWidget(clear_button)

        log_group_layout = QVBoxLayout()
        log_group_layout.addLayout(log_controls)
        log_group_layout.addWidget(self._log_view)

        log_group = QGroupBox("Logs")
        log_group.setLayout(log_group_layout)

        layout.addWidget(log_group)

        self.setCentralWidget(central)
        self._app = QApplication.instance()
        if self._app is not None:
            self._app.aboutToQuit.connect(self._handle_app_quit)

        self._serial_bridge: Optional[SerialBridge] = None
        self._serial_connected = False
        self._serial_config = serial_config
        self._valid_buttons = set(self._button_widgets.keys())
        self._logger = get_logger("virtual_controller")
        self._log_history: list[tuple[str, str]] = []
        self._log_filter_level = "INFO"
        self._pending_remote_logs: set[tuple[str, str]] = set()
        self._update_search_controls()

        self._set_controls_enabled(False)

        if serial is None:
            self._log_warning(
                "PySerial not available. Install with `pip install pyserial` to enable communication."
            )
            self._status_label.setText("Status: PySerial missing")
        else:
            port = serial_config.port or (self._auto_detect_port() if serial_config.auto_detect else None)
            if port:
                self._log_info(f"Connecting to {port} @ {serial_config.baudrate}...")
                self._open_serial(port, serial_config.baudrate)
            else:
                self._status_label.setText("Status: Select a serial port with --port")
                self._log_info("No serial port provided; launch with --port PATH or enable auto-detect support.")

    def closeEvent(self, event):  # noqa: D401 - Qt override
        self._cleanup()
        event.accept()
        super().closeEvent(event)

    def _handle_app_quit(self):
        self._cleanup()

    def _cleanup(self):
        if self._serial_bridge is not None:
            try:
                self._serial_bridge.stop()
            finally:
                self._serial_bridge = None

    # ------------------------------------------------------------------
    # UI construction helpers

    def _build_dpad_group(self):
        group = QGroupBox("D-Pad")
        grid = QGridLayout()
        group.setLayout(grid)

        grid.addWidget(self._make_button("UP"), 0, 1)
        grid.addWidget(self._make_button("LEFT"), 1, 0)
        grid.addWidget(self._make_button("RIGHT"), 1, 2)
        grid.addWidget(self._make_button("DOWN"), 2, 1)

        return group

    def _build_face_group(self):
        group = QGroupBox("Face Buttons")
        grid = QGridLayout()
        group.setLayout(grid)

        labels = (
            ("X", 0, 0),
            ("Y", 0, 1),
            ("R1", 0, 2),
            ("R2", 0, 3),
            ("A", 1, 0),
            ("B", 1, 1),
            ("L1", 1, 2),
            ("L2", 1, 3),
        )
        for name, row, col in labels:
            grid.addWidget(self._make_button(name), row, col)

        return group

    def _build_system_group(self):
        group = QGroupBox("System")
        row = QHBoxLayout()
        group.setLayout(row)

        for name in SYSTEM_BUTTONS:
            row.addWidget(self._make_button(name))

        return group

    def _make_button(self, name: str) -> QPushButton:
        button = QPushButton(name)
        button.setEnabled(False)
        button.pressed.connect(lambda n=name: self._handle_button_press(n))
        button.released.connect(lambda n=name: self._handle_button_release(n))
        self._button_widgets[name] = button
        return button

    # ------------------------------------------------------------------
    # Serial management

    def _open_serial(self, port: str, baudrate: int):
        self._serial_bridge = SerialBridge(port, baudrate)
        self._serial_bridge.line_received.connect(self._handle_serial_line)
        self._serial_bridge.connection_changed.connect(self._handle_connection_change)
        self._serial_bridge.error.connect(self._handle_serial_error)
        self._serial_bridge.start()

    def _auto_detect_port(self) -> Optional[str]:
        if list_ports is None:
            return None
        for candidate in list_ports.comports():
            description = (candidate.description or "").lower()
            manufacturer = (candidate.manufacturer or "").lower()
            if "circuitpy" in description or "circuitpython" in description or "adafruit" in manufacturer:
                return candidate.device
        return None

    def _handle_connection_change(self, connected: bool):
        self._serial_connected = connected
        if connected:
            self._status_label.setText("Status: Connected")
            self._log_info("Serial connected.")
            self._set_controls_enabled(True)
            self._send_command("STATE?")
        else:
            self._status_label.setText("Status: Disconnected")
            self._log_info("Serial disconnected.")
            self._set_controls_enabled(False)
            self._update_button_states(set())

    def _handle_serial_error(self, message: str):
        self._log_error(f"Serial error: {message}")

    def _handle_serial_line(self, line: str):
        if not line.startswith("DBG "):
            level = self._infer_level(line) or "INFO"
            self._record_log(level, line)
            return

        parts = line.split(" ", 2)
        if len(parts) < 3:
            level = self._infer_level(line) or "INFO"
            self._record_log(level, line)
            return
        _, label, payload = parts
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            level = self._infer_level(payload) or "INFO"
            self._record_log(level, f"{label}: {payload}")
            return

        label = label.upper()
        if label == "STATE":
            self._handle_state_message(data)
        elif label == "READY":
            self._handle_ready_message(data)
            self._record_log("INFO", "Device reported ready.")
        elif label == "LOG":
            level = data.get("level", "INFO")
            logger = data.get("logger") or "firmware"
            message = data.get("message", "")
            self._record_log(level, f"{logger}: {message}")
        else:
            text = data.get("message") if isinstance(data, dict) and "message" in data else json.dumps(data)
            normalized_label = label.upper()
            level_aliases = {
                "WARN": "WARNING",
                "ERR": "ERROR",
            }
            level = level_aliases.get(normalized_label, normalized_label)
            if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                self._record_log(level, text)
            else:
                fallback_level = self._infer_level(text) or "INFO"
                self._record_log(fallback_level, f"{label}: {text}")

    # ------------------------------------------------------------------
    # Message handlers

    def _handle_state_message(self, payload: Dict[str, object]):
        buttons = set(payload.get("buttons", []))
        self._update_button_states(buttons)

    def _handle_ready_message(self, payload: Dict[str, object]):
        buttons = payload.get("buttons")
        if isinstance(buttons, Iterable):
            normalized = {str(name).upper() for name in buttons}
            if normalized:
                self._valid_buttons = normalized
                missing = normalized - set(self._button_widgets.keys())
                if missing:
                    self._record_log("WARNING", f"Ready message references unknown buttons: {sorted(missing)}")
        self._status_label.setText("Status: Ready")

    # ------------------------------------------------------------------
    # UI helpers

    def _log_with_level(self, level: str, message: str):
        base_level = str(level).upper()
        detected = self._infer_level(message)
        level_name = detected if detected is not None else base_level
        try:
            numeric_level = get_level_by_name(level_name)
        except ValueError:
            numeric_level = INFO
            level_name = "INFO"

        if self._serial_connected and self._serial_bridge is not None:
            if self._send_log_command(level_name, message):
                display_message = f"{self._logger_name}: {message}"
                display = self._format_display(level_name, display_message)
                self._pending_remote_logs.add((level_name, display))
                self._append_log_entry(level_name, display)
                return

        # Fallback to local logging when not connected or transmission fails.
        self._logger.log(numeric_level, message)
        self._record_log(level_name, message)

    def _log_info(self, message: str):
        self._log_with_level("INFO", message)

    def _log_warning(self, message: str):
        self._log_with_level("WARNING", message)

    def _log_error(self, message: str):
        self._log_with_level("ERROR", message)

    def _log_debug(self, message: str):
        self._log_with_level("DEBUG", message)

    def _record_log(self, level_name: str, message: str):
        level_name = str(level_name).upper()
        display = self._format_display(level_name, message)
        entry = (level_name, display)
        if entry in self._pending_remote_logs:
            self._pending_remote_logs.discard(entry)
            return
        self._append_log_entry(level_name, display)

    def _append_log_entry(self, level_name: str, display: str):
        entry = (level_name, display)
        self._log_history.append(entry)
        if self._should_display(level_name):
            self._log_view.append(display)
        self._update_search_controls()

    @staticmethod
    def _format_display(level_name: str, message: str) -> str:
        prefix = f"[{level_name}]"
        normalized = message.lstrip()
        return message if normalized.startswith(prefix) else f"{prefix} {message}"

    def _send_log_command(self, level_name: str, message: str) -> bool:
        if self._serial_bridge is None:
            return False
        sanitized = message.replace("\r", " ").replace("\n", "\\n")
        command = f"LOG {level_name} {self._logger_name} {sanitized}"
        try:
            self._send_command(command, echo=False)
            return True
        except Exception:
            return False

    @staticmethod
    def _infer_level(message: str) -> Optional[str]:
        stripped = message.lstrip()
        if stripped.startswith("["):
            closing = stripped.find("]")
            if 0 < closing <= 12:
                candidate = stripped[1:closing].upper()
                if candidate in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
                    return candidate
        return None

    def _handle_log_filter_change(self, text: str):
        self._log_filter_level = text.upper()
        self._refresh_log_view()

    def _handle_clear_logs(self):
        self._log_history.clear()
        self._pending_remote_logs.clear()
        self._log_view.clear()
        self._search_cursor = None
        self._restart_search()
        self._update_search_controls()

    def _handle_save_logs(self):
        if not self._log_history:
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save Log",
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8") as fh:
                for _, display in self._log_history:
                    fh.write(display)
                    fh.write("\n")
        except Exception as exc:  # pragma: no cover - filesystem issues
            self._record_log("ERROR", f"Failed to save log: {exc}")

    def _refresh_log_view(self):
        self._log_view.clear()
        for level_name, display in self._log_history:
            if self._should_display(level_name):
                self._log_view.append(display)
        # After rebuilding the view, reset search highlight if needed.
        self._restart_search()
        self._update_search_controls()

    def _should_display(self, level_name: str) -> bool:
        if self._log_filter_level == "ALL":
            return True
        level_value = _LEVEL_PRIORITY.get(level_name, INFO)
        threshold = _LEVEL_PRIORITY.get(self._log_filter_level, INFO)
        return level_value >= threshold

    def _handle_search_text_change(self, text: str):
        self._search_term = text
        self._search_cursor = None
        self._update_search_controls()
        if text:
            self._restart_search()
        else:
            cursor = self._log_view.textCursor()
            cursor.movePosition(QTextCursor.End)
            self._log_view.setTextCursor(cursor)

    def _search_next(self):
        self._find_match(forward=True)

    def _search_previous(self):
        self._find_match(forward=False)

    def _find_match(self, forward: bool, restart: bool = False):
        if not self._search_term:
            return

        document = self._log_view.document()
        flags = QTextDocument.FindFlags()
        if not forward:
            flags |= QTextDocument.FindBackward

        if restart or self._search_cursor is None:
            cursor = QTextCursor(document)
            cursor.movePosition(QTextCursor.Start if forward else QTextCursor.End)
        else:
            cursor = QTextCursor(document)
            if forward:
                cursor.setPosition(self._search_cursor.selectionEnd())
            else:
                cursor.setPosition(self._search_cursor.selectionStart())

        result = document.find(self._search_term, cursor, flags)
        if result.isNull():
            wrap_cursor = QTextCursor(document)
            wrap_cursor.movePosition(QTextCursor.Start if forward else QTextCursor.End)
            result = document.find(self._search_term, wrap_cursor, flags)
        if result.isNull():
            self._search_cursor = None
            return

        self._search_cursor = result
        self._log_view.setTextCursor(result)
        self._log_view.ensureCursorVisible()

    def _restart_search(self):
        if not self._search_term:
            self._search_cursor = None
            return
        self._search_cursor = None
        self._find_match(forward=True, restart=True)

    def _update_search_controls(self):
        active = bool(self._search_term)
        self._search_prev_button.setEnabled(active)
        self._search_next_button.setEnabled(active)

    def _set_controls_enabled(self, enabled: bool):
        for button in self._button_widgets.values():
            button.setEnabled(enabled)

    def _update_button_states(self, active: Iterable[str]):
        active_set = {name.upper() for name in active}
        for name, button in self._button_widgets.items():
            button.setDown(name in active_set)

    # ------------------------------------------------------------------
    # Button event handlers

    def _handle_button_press(self, name: str):
        if not self._serial_connected:
            self._log_debug(f"Ignoring PRESS {name}; serial not connected.")
            return
        if name not in self._valid_buttons:
            self._log_warning(f"Ignoring PRESS {name}; button not recognised by device.")
            return
        self._send_command(f"PRESS {name}")

    def _handle_button_release(self, name: str):
        if not self._serial_connected:
            self._log_debug(f"Ignoring RELEASE {name}; serial not connected.")
            return
        if name not in self._valid_buttons:
            self._log_warning(f"Ignoring RELEASE {name}; button not recognised by device.")
            return
        self._send_command(f"RELEASE {name}")

    def _send_command(self, command: str, *, echo: bool = True):
        if self._serial_bridge is None:
            self._log_warning(f"Cannot send '{command}'; serial bridge unavailable.")
            return
        if echo:
            self._log_debug(f"-> {command}")
        self._serial_bridge.send(command)


def _parse_args(argv: Sequence[str]) -> tuple[SerialConfig, Sequence[str]]:
    parser = argparse.ArgumentParser(description="Debugger UI for the Bluetooth HID arcade stick.", add_help=False)
    parser.add_argument("--port", help="Serial port connected to the board (autodetected when possible).")
    parser.add_argument("--baudrate", type=int, default=DEFAULT_BAUDRATE, help="Serial baudrate (default: %(default)s).")
    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable automatic port detection when --port is not supplied.",
    )
    parser.add_argument("-h", "--help", action="help", help="Show this help message and exit.")
    known, remaining = parser.parse_known_args(argv[1:])
    config = SerialConfig(
        port=known.port,
        baudrate=known.baudrate,
        auto_detect=not known.no_auto_detect,
    )
    # Preserve argv[0] for Qt; QApplication expects the executable path at index 0.
    qt_args = [argv[0], *remaining]
    return config, qt_args


def run(argv: Optional[Sequence[str]] = None):
    """Launch the debugger UI."""
    raw_argv = list(argv if argv is not None else sys.argv)
    serial_config, qt_args = _parse_args(raw_argv)
    app = QApplication(qt_args)
    window = DebuggerWindow(serial_config)
    window.resize(960, 640)
    window.show()
    return app.exec()


def main():
    return run()


if __name__ == "__main__":
    sys.exit(main())
