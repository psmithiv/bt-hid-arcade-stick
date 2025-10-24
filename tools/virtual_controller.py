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
import time
import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence
from queue import Empty, Queue

from PySide6.QtCore import Q_ARG, QObject, QThread, Qt, QMetaObject, Signal, Slot, QEvent, QTimer
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
    QGraphicsDropShadowEffect,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from PySide6.QtGui import QColor, QTextCursor, QTextDocument, QTextCharFormat, QFontDatabase

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from firmware_logging import INFO, get_level_by_name

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
    print_logs: bool = False


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
        self._outgoing: Queue[bytes] = Queue()
        self._timer: Optional[QTimer] = None
        self._connected = False

    @Slot()
    def start(self):
        try:
            self._serial = serial.Serial(self._port, self._baudrate, timeout=0.0, write_timeout=0.0)
            self._connected = True
            self.connected_changed.emit(True)
        except Exception as exc:  # pragma: no cover - hardware interaction
            self.error.emit(f"Failed to open {self._port}: {exc}")
            self.connected_changed.emit(False)
            self.finished.emit()
            return

        self._timer = QTimer(self)
        self._timer.setInterval(10)
        self._timer.timeout.connect(self._poll_serial)
        self._timer.start()

    @Slot(str)
    def send(self, text: str):
        """Accept text from the UI thread and queue it for transmission."""
        payload = text if text.endswith("\n") else f"{text}\n"
        self._outgoing.put(payload.encode("utf-8"))

    @Slot()
    def stop(self):
        self._stop_requested = True

    def _poll_serial(self):
        """Process queued writes then consume any available incoming lines."""
        if self._stop_requested:
            self._shutdown()
            return
        self._flush_outgoing()
        if self._stop_requested:
            self._shutdown()
            return
        self._read_incoming()

    def _flush_outgoing(self):
        """Drain the outgoing queue, writing each payload to the serial port."""
        if self._serial is None:
            return
        while True:
            try:
                payload = self._outgoing.get_nowait()
            except Empty:
                break
            try:
                self._serial.write(payload)
                self._serial.flush()
            except Exception as exc:  # pragma: no cover - hardware interaction
                self.error.emit(f"Serial write failed: {exc}")
                self._stop_requested = True
                break

    def _read_incoming(self):
        """Read encoded lines from the serial port and emit them via Qt signals."""
        if self._serial is None:
            return
        try:
            while True:
                line = self._serial.readline()
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace").strip()
                if decoded:
                    self.line_received.emit(decoded)
        except Exception as exc:  # pragma: no cover - hardware interaction
            self.error.emit(f"Serial read failed: {exc}")
            self._stop_requested = True

    def _shutdown(self):
        """Release resources and notify listeners that the worker finished."""
        if self._timer is not None:
            self._timer.stop()
            self._timer.timeout.disconnect()
            self._timer.deleteLater()
            self._timer = None
        if self._connected:
            self.connected_changed.emit(False)
            self._connected = False
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:  # pragma: no cover - best-effort close
                pass
            self._serial = None
        self.finished.emit()


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
        """Stop the worker thread and tear down the serial bridge."""
        if self._thread is None or self._worker is None:
            return
        if self._thread.isRunning():
            QMetaObject.invokeMethod(self._worker, "stop", Qt.QueuedConnection)
            self._thread.quit()
            self._thread.wait()
        if self._thread is not None:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None

    def send(self, text: str):
        """Enqueue a line of text to be transmitted over serial."""
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

    _LEVEL_COLORS = {
        "DEBUG": QColor("#6c8cff"),
        "INFO": QColor("#0aa15f"),
        "WARNING": QColor("#d9a406"),
        "ERROR": QColor("#d65b5b"),
        "CRITICAL": QColor("#b01e1e"),
    }
    _TIMESTAMP_COLOR = QColor("#7a7a7a")
    _LOGGER_COLOR = QColor("#2495b7")
    _EVENT_COLOR = QColor("#c47f16")

    def __init__(self, serial_config: SerialConfig):
        super().__init__()
        self.setWindowTitle("Arcade Stick Debugger")

        central = QWidget()
        layout = QVBoxLayout()
        central.setLayout(layout)

        status_row = QHBoxLayout()
        self._status_label = QLabel("Serial: Disconnected")
        self._ble_status_label = QLabel("-  BLE: Unknown")
        status_row.addWidget(self._status_label)
        status_row.addWidget(self._ble_status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        controls_layout = QHBoxLayout()
        self._button_widgets = {}
        controls_layout.addWidget(self._build_dpad_group(), stretch=1)
        controls_layout.addWidget(self._build_face_group(), stretch=1)
        layout.addLayout(controls_layout)

        layout.addWidget(self._build_system_group())

        self._category_label = QLabel("Category:")
        self._category_filter = QComboBox()
        self._category_filter.addItems(["ALL", "LOG", "RAW"])
        self._category_filter.setCurrentText("LOG")
        self._category_filter.currentTextChanged.connect(self._handle_category_filter_change)
        self._category_filter_value = "LOG"
        self._log_level_label = QLabel("Log level:")
        self._log_filter = QComboBox()
        self._log_filter.addItems(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
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
        self._search_glow: Optional[QGraphicsDropShadowEffect] = None

        self._log_view = QTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        self._log_view.setPlaceholderText("Waiting for device logs...")
        log_controls = QHBoxLayout()
        log_controls.addWidget(self._category_label)
        log_controls.addWidget(self._category_filter)
        log_controls.addWidget(self._log_level_label)
        log_controls.addWidget(self._log_filter)
        log_controls.addStretch()
        log_controls.addWidget(QLabel("Search:"))
        self._search_input.setStyleSheet(
            """
            QLineEdit {
                border-radius: 6px;
                padding: 3px 5px;
                border: 1px solid #bcbcbc;
            }
            QLineEdit:focus {
                border: 1px solid #666666;
            }
            """
        )
        self._search_glow = QGraphicsDropShadowEffect(self._search_input)
        self._search_glow.setBlurRadius(12)
        self._search_glow.setOffset(0, 0)
        self._search_glow.setColor(QColor(80, 80, 80, 160))
        self._search_glow.setEnabled(False)
        self._search_input.setGraphicsEffect(self._search_glow)
        self._search_input.installEventFilter(self)
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
        self._log_history: list[tuple[str, str, Optional[Dict[str, object]], str, str]] = []
        self._log_filter_level = "INFO"
        self._print_logs = serial_config.print_logs
        self._update_search_controls()
        self._update_log_filter_visibility()

        self._set_controls_enabled(False)
        self._ble_status_label.setText("-  BLE: Waiting for serial...")

        if serial is None:
            self._log_warning(
                "PySerial not available. Install with `pip install pyserial` to enable communication."
            )
            self._status_label.setText("Serial: PySerial missing")
        else:
            port = serial_config.port or (self._auto_detect_port() if serial_config.auto_detect else None)
            if port:
                self._log_info(f"Connecting to {port} @ {serial_config.baudrate}...")
                self._open_serial(port, serial_config.baudrate)
            else:
                self._status_label.setText("Serial: Select a serial port with --port")
                self._log_info("No serial port provided; launch with --port PATH or enable auto-detect support.")

    def closeEvent(self, event):  # noqa: D401 - Qt override
        self._cleanup()
        event.accept()
        super().closeEvent(event)

    def _handle_app_quit(self):
        """Ensure background resources stop when the application exits."""
        self._cleanup()

    def _cleanup(self):
        """Stop the serial bridge if it is currently active."""
        if self._serial_bridge is not None:
            try:
                self._serial_bridge.stop()
            finally:
                self._serial_bridge = None

    # ------------------------------------------------------------------
    # UI construction helpers

    def _build_dpad_group(self):
        """Construct the D-pad button cluster."""
        group = QGroupBox("D-Pad")
        grid = QGridLayout()
        group.setLayout(grid)

        grid.addWidget(self._make_button("UP"), 0, 1)
        grid.addWidget(self._make_button("LEFT"), 1, 0)
        grid.addWidget(self._make_button("RIGHT"), 1, 2)
        grid.addWidget(self._make_button("DOWN"), 2, 1)

        return group

    def _build_face_group(self):
        """Construct the face button cluster."""
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
        """Construct the system button row (HOME/START/etc.)."""
        group = QGroupBox("System")
        row = QHBoxLayout()
        group.setLayout(row)

        for name in SYSTEM_BUTTONS:
            row.addWidget(self._make_button(name))

        return group

    def _make_button(self, name: str) -> QPushButton:
        """Create a QPushButton wired to send virtual press/release commands."""
        button = QPushButton(name)
        button.setEnabled(False)
        button.pressed.connect(lambda n=name: self._handle_button_press(n))
        button.released.connect(lambda n=name: self._handle_button_release(n))
        self._button_widgets[name] = button
        return button

    # ------------------------------------------------------------------
    # Serial management

    def _open_serial(self, port: str, baudrate: int):
        """Instantiate the serial bridge and connect signal handlers."""
        self._serial_bridge = SerialBridge(port, baudrate)
        self._serial_bridge.line_received.connect(self._handle_serial_line)
        self._serial_bridge.connection_changed.connect(self._handle_connection_change)
        self._serial_bridge.error.connect(self._handle_serial_error)
        self._serial_bridge.start()

    def _auto_detect_port(self) -> Optional[str]:
        """Return the first serial port that looks like a CircuitPython device."""
        if list_ports is None:
            return None
        for candidate in list_ports.comports():
            description = (candidate.description or "").lower()
            manufacturer = (candidate.manufacturer or "").lower()
            if "circuitpy" in description or "circuitpython" in description or "adafruit" in manufacturer:
                return candidate.device
        return None

    def _handle_connection_change(self, connected: bool):
        """Update UI state and logs when the serial link connects or drops."""
        self._serial_connected = connected
        if connected:
            self._status_label.setText("Serial: Connected")
            self._log_info("Serial connected.")
            self._set_controls_enabled(True)
            self._send_command("STATE?")
            self._ble_status_label.setText("-  BLE: Awaiting status...")
        else:
            self._status_label.setText("Serial: Disconnected")
            self._log_info("Serial disconnected.")
            self._set_controls_enabled(False)
            self._update_button_states(set())
            self._ble_status_label.setText("-  BLE: Unknown")

    def _handle_serial_error(self, message: str):
        """Surface serial errors to the log view."""
        self._log_error(f"Serial error: {message}")

    def _handle_serial_line(self, line: str):
        """Decode a single line received from the firmware."""
        if not line:
            return

        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            level = self._infer_level(line) or "INFO"
            self._record_log("RAW", level, None, line)
            return

        msg_type = str(data.get("type", "")).upper()
        category = self._normalize_category(msg_type)

        if msg_type == "STATE":
            self._handle_state_message(data)
        elif msg_type == "READY":
            self._handle_ready_message(data)
        if str(data.get("source", "")).upper() == "BLE":
            self._handle_ble_status(data)

        level = data.get("level", "INFO")
        self._record_log(category, level, data, line)

    # ------------------------------------------------------------------
    # Message handlers

    def _handle_state_message(self, payload: Dict[str, object]):
        """Synchronize button widgets with the state reported by firmware."""
        buttons = set(payload.get("buttons", []))
        self._update_button_states(buttons)

    def _handle_ready_message(self, payload: Dict[str, object]):
        """Refresh the valid button list once the firmware advertises it."""
        buttons = payload.get("buttons")
        if isinstance(buttons, Iterable):
            normalized = {str(name).upper() for name in buttons}
            if normalized:
                self._valid_buttons = normalized
        self._status_label.setText("Serial: Ready")

    def _handle_ble_status(self, payload: Dict[str, object]):
        """Update BLE status label based on events from the firmware."""
        message = payload.get("message")
        event = str(payload.get("event", "") or "").upper()
        if isinstance(message, str) and message.strip():
            text = message.strip()
        elif event:
            text = event.title()
        else:
            text = "Status Unknown"
        mode = payload.get("mode")
        if mode:
            text = f"{text} ({mode})"
        active = payload.get("active")
        if event == "PAIRING_ACTIVE":
            suffix = "active" if bool(active) else "inactive"
            text = f"Pairing {suffix}"
        self._ble_status_label.setText(f"-  BLE: {text}")

    # ------------------------------------------------------------------
    # UI helpers

    def _log_with_level(self, level: str, message: str):
        """
        Forward a UI-originated log message to firmware when possible.
        Falls back to recording the entry locally and only mirrors it to stdout
        when the `--print-logs` flag enabled `_print_logs`.
        """
        base_level = str(level).upper()
        detected = self._infer_level(message)
        level_name = detected if detected is not None else base_level
        try:
            get_level_by_name(level_name)
        except ValueError:
            level_name = "INFO"

        if self._serial_connected and self._serial_bridge is not None:
            if self._send_log_command(level_name, message):
                return

        # Fallback to local logging when not connected or transmission fails.
        local_record = {
            "type": "log",
            "level": level_name,
            "logger": self._logger_name,
            "message": message,
            "timestamp": time.monotonic(),
        }
        self._record_log("LOG", level_name, local_record, json.dumps(local_record))

    def _log_info(self, message: str):
        self._log_with_level("INFO", message)

    def _log_warning(self, message: str):
        self._log_with_level("WARNING", message)

    def _log_error(self, message: str):
        self._log_with_level("ERROR", message)

    def _log_debug(self, message: str):
        self._log_with_level("DEBUG", message)

    def _record_log(self, category: str, level_name: str, parsed: Optional[Dict[str, object]], raw_line: str):
        """Persist a log entry in the UI, optionally echoing to stdout if requested."""
        category = (category or "RAW").upper()
        level_name = str(level_name).upper()
        display_ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        entry = (category, level_name, parsed, raw_line, display_ts)
        self._log_history.append(entry)
        if self._should_display(category, level_name):
            self._append_formatted_entry(entry)
        if self._print_logs:
            try:
                print(self._format_plain_text(entry))
            except Exception:
                pass
        self._update_search_controls()

    def _handle_category_filter_change(self, text: str):
        """Update the active message category filter."""
        self._category_filter_value = text.upper()
        self._update_log_filter_visibility()
        self._refresh_log_view()

    def _update_log_filter_visibility(self):
        """Show or hide the log level controls based on category selection."""
        is_log = self._category_filter_value in {"ALL", "LOG"}
        self._log_level_label.setVisible(is_log)
        self._log_filter.setVisible(is_log)

    def _send_log_command(self, level_name: str, message: str) -> bool:
        """Best-effort attempt to relay host logs through the firmware."""
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

    @staticmethod
    def _normalize_category(msg_type: str) -> str:
        upper = (msg_type or "").upper()
        if upper == "LOG" or not upper:
            return "LOG"
        return "RAW"

    def _handle_log_filter_change(self, text: str):
        """Adjust the visible log level threshold."""
        self._log_filter_level = text.upper()
        self._refresh_log_view()

    def _handle_clear_logs(self):
        """Remove all log entries from history and the view."""
        self._log_history.clear()
        self._log_view.clear()
        self._search_cursor = None
        self._restart_search()
        self._update_search_controls()

    def _append_formatted_entry(self, entry: tuple[str, str, Optional[Dict[str, object]], str]):
        category, level_name, parsed, raw_line, display_ts = entry
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self._log_view.toPlainText():
            cursor.insertBlock()

        if category == "LOG" and isinstance(parsed, dict):
            self._insert_log_line(cursor, level_name, parsed, display_ts)
        elif isinstance(parsed, dict):
            text = self._format_plain_text(entry)
            color = self._EVENT_COLOR if category != "RAW" else None
            self._insert_text(cursor, text, color)
        else:
            self._insert_text(cursor, raw_line)

    def _insert_log_line(self, cursor: QTextCursor, level_name: str, parsed: Dict[str, object], display_ts: str):
        ts_value = self._safe_float(parsed.get("timestamp"))
        logger_name = str(parsed.get("logger", "") or "")
        message = parsed.get("message")
        components: list[tuple[str, Optional[QColor]]] = []
        components.append((display_ts, self._TIMESTAMP_COLOR))
        level_color = self._LEVEL_COLORS.get(level_name, self._LEVEL_COLORS.get("INFO", QColor("#0aa15f")))
        components.append((level_name, level_color))
        if logger_name:
            components.append((logger_name, self._LOGGER_COLOR))
        if message is None:
            message_text = ""
        else:
            message_text = str(message)
        message_text = message_text.replace("\n", "  ")
        for index, (text, color) in enumerate(components):
            if index > 0:
                self._insert_text(cursor, " ")
            self._insert_text(cursor, text, color)
        if message_text:
            if components:
                self._insert_text(cursor, " – ")
            self._insert_text(cursor, message_text)

    @staticmethod
    def _insert_text(cursor: QTextCursor, text: str, color: Optional[QColor] = None, weight: Optional[int] = None):
        if not text:
            return
        fmt = QTextCharFormat()
        if color is not None:
            fmt.setForeground(color)
        if weight is not None:
            fmt.setFontWeight(weight)
        cursor.insertText(text, fmt)

    @staticmethod
    def _safe_float(value: Optional[object]) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _format_plain_text(self, entry: tuple[str, str, Optional[Dict[str, object]], str]) -> str:
        category, level_name, parsed, raw_line, display_ts = entry
        if category == "LOG" and isinstance(parsed, dict):
            ts_value = self._safe_float(parsed.get("timestamp"))
            logger_name = str(parsed.get("logger", "") or "")
            message = parsed.get("message")
            if message is None:
                message_text = ""
            else:
                message_text = str(message)
            message_text = message_text.replace("\n", "  ")
            ts_text = f"{display_ts} " if display_ts else ""
            logger_text = f"{logger_name} " if logger_name else ""
            separator = "– " if message_text else ""
            return f"{ts_text}{level_name:<8} {logger_text}{separator}{message_text}".strip()
        if isinstance(parsed, dict):
            message = parsed.get("message")
            if message is not None:
                msg = str(message).replace("\n", "  ")
                ts_value = self._safe_float(parsed.get("timestamp"))
                parts = []
                if display_ts:
                    parts.append(display_ts)
                event_type = str(parsed.get("type", "EVENT")).upper()
                parts.append(event_type)
                source = parsed.get("source")
                if source:
                    parts.append(str(source))
                parts.append(msg)
                return " ".join(parts)
        return raw_line

    def _handle_save_logs(self):
        """Persist the current log history to disk via a file dialog."""
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
                for entry in self._log_history:
                    fh.write(self._format_plain_text(entry))
                    fh.write("\n")
        except Exception as exc:  # pragma: no cover - filesystem issues
            self._record_log("LOG", "ERROR", f"Failed to save log: {exc}")

    def _refresh_log_view(self):
        """Rebuild the visible log pane based on the active filter."""
        self._log_view.clear()
        for entry in self._log_history:
            category, level_name, _, _, _ = entry
            if self._should_display(category, level_name):
                self._append_formatted_entry(entry)
        # After rebuilding the view, reset search highlight if needed.
        self._restart_search()
        self._update_search_controls()

    def _should_display(self, category: str, level_name: str) -> bool:
        """Return True when an entry passes the active category/level filters."""
        if self._category_filter_value != "ALL" and category != self._category_filter_value:
            return False
        if category == "LOG":
            level_value = _LEVEL_PRIORITY.get(level_name, INFO)
            threshold = _LEVEL_PRIORITY.get(self._log_filter_level, INFO)
            return level_value >= threshold
        return True

    def _handle_search_text_change(self, text: str):
        """Update the search query and move the caret when necessary."""
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
        """Advance to the next search match."""
        self._find_match(forward=True)

    def _search_previous(self):
        """Move to the previous search match."""
        self._find_match(forward=False)

    def _find_match(self, forward: bool, restart: bool = False):
        """Advance the search cursor in the requested direction, wrapping if needed."""
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
        """Reset any existing search highlight and start over."""
        if not self._search_term:
            self._search_cursor = None
            return
        self._search_cursor = None
        self._find_match(forward=True, restart=True)

    def _update_search_controls(self):
        """Enable/disable search navigation buttons based on the current query."""
        active = bool(self._search_term)
        self._search_prev_button.setEnabled(active)
        self._search_next_button.setEnabled(active)

    def eventFilter(self, obj, event):
        if obj is self._search_input:
            if event.type() == QEvent.FocusIn:
                if self._search_glow is not None:
                    self._search_glow.setEnabled(True)
            elif event.type() == QEvent.FocusOut:
                if self._search_glow is not None:
                    self._search_glow.setEnabled(False)
        return super().eventFilter(obj, event)

    def _set_controls_enabled(self, enabled: bool):
        """Enable or disable all controller buttons in the UI."""
        for button in self._button_widgets.values():
            button.setEnabled(enabled)

    def _update_button_states(self, active: Iterable[str]):
        """Update button pressed visuals based on the provided active set."""
        active_set = {name.upper() for name in active}
        for name, button in self._button_widgets.items():
            button.setDown(name in active_set)

    # ------------------------------------------------------------------
    # Button event handlers

    def _handle_button_press(self, name: str):
        """Send a virtual button press if the device recognizes the button."""
        if not self._serial_connected:
            self._log_debug(f"Ignoring PRESS {name}; serial not connected.")
            return
        if name not in self._valid_buttons:
            self._log_warning(f"Ignoring PRESS {name}; button not recognised by device.")
            return
        self._send_command(f"PRESS {name}")

    def _handle_button_release(self, name: str):
        """Send a virtual button release if the device recognizes the button."""
        if not self._serial_connected:
            self._log_debug(f"Ignoring RELEASE {name}; serial not connected.")
            return
        if name not in self._valid_buttons:
            self._log_warning(f"Ignoring RELEASE {name}; button not recognised by device.")
            return
        self._send_command(f"RELEASE {name}")

    def _send_command(self, command: str, *, echo: bool = True):
        """Transmit a raw command string to the firmware via the serial bridge."""
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
    parser.add_argument(
        "--print-logs",
        action="store_true",
        help="Echo raw log lines to stdout.",
    )
    parser.add_argument("-h", "--help", action="help", help="Show this help message and exit.")
    known, remaining = parser.parse_known_args(argv[1:])
    config = SerialConfig(
        port=known.port,
        baudrate=known.baudrate,
        auto_detect=not known.no_auto_detect,
        print_logs=known.print_logs,
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
