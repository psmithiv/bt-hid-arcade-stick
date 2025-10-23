# Bluetooth HID Arcade Stick Firmware

This project is a CircuitPython-based firmware and companion desktop tooling for a Bluetooth / USB arcade stick. It provides:

- A modular firmware that maps physical inputs to Bluetooth Low Energy (BLE) and USB HID reports.
- A serial debug interface that exposes state, accepts virtual button commands, and mirrors firmware logs.
- A desktop “Virtual Controller” UI for development workflows.

The codebase is organized so each concern (hardware drivers, communication stacks, logging, debug tooling) remains isolated while flowing through a shared logging and state pipeline.

---

## Documentation

Project documentation is now generated with [Sphinx](https://www.sphinx-doc.org/).
Use the provided configuration under `docs/` to build HTML pages that include an
overview, hardware wiring guide, and API reference pulled directly from the
source docstrings.

```bash
pip install sphinx
sphinx-build -b html docs build/html
open build/html/index.html  # macOS; adjust for your platform
```

For CI or quick local validation, run the helper script alongside the deploy
utility:

```bash
python scripts/build_docs.py
```

The Sphinx site supersedes the long-form content that previously lived in this
README. Use the generated docs for deep dives; the sections below capture a
concise project status.

---

## Current Status

- **DONE**
  - Structured logging pipeline with JSON output and Sphinx-backed documentation.
  - Debounced hardware input polling wired into the HID controller.
  - Virtual controller UI sending/receiving serial commands with searchable logs.
  - CI helper (`scripts/build_docs.py`) and GitHub Actions workflow that build docs on pushes/PRs.
- **NEXT**
  - Validate BLE HID path end-to-end (advertising, bonding, reconnection, state mirroring in the UI).
  - Finalize pin mapping on production hardware and capture wiring notes in the docs.
  - Extend automated tests for host tooling and critical firmware logic.
- **BACKLOG**
  - Power-management features (battery telemetry, sleep hooks).
  - Broader HID feature set (report customization, macros).
  - Packaging for distribution (frozen bundles, installer scripts).

---

## Module Highlights

Refer to the full API reference in `/docs/reference.rst` (or the generated
HTML) for comprehensive documentation. Key pieces:

- `code.py` – firmware entry point and cooperative main loop.
- `config.py` – centralized button map, debounce tuning, BLE/USB options, log level.
- `input_manager.py` – active-low GPIO polling with debouncing (`InputEvents`).
- `hid_controller.py` – translates logical button sets into HID reports.
- `ble_manager.py` – BLE advertising, pairing, and event notifications (BLE work in progress).
- `debug_interface.py` – serial debug protocol used by the desktop UI.
- `tools/virtual_controller.py` – Qt UI for virtual inputs, logs, and status.

---

## Hardware Notes

- Buttons are wired active-low with pull-up resistors; adjust `config.PIN_MAP`
  to match the production harness (see `docs/hardware.rst` for the full table).
- Dedicated pairing button (optional) should be configured via
  `config.PAIRING_BUTTON_PIN` and held for `PAIRING_HOLD_MS` to enter pairing mode.

---

## Logging & Debugging

- Logs are JSON objects emitted via `firmware_logging` (consumed by the virtual controller and any serial listener).
- The debug interface surfaces state snapshots, BLE events, and replies to commands such as `STATE?`, `PRESS`, `LOG`.
- Message categories:
  - `type: "log"` – structured log entries with `level`, `logger`, `message`, `timestamp`.
  - `type: "state"` – current button snapshot used to drive the UI state.
  - `type: "info" / "warn" / "err"` – status events (e.g., BLE lifecycle, pairing results); may include a `source`.
- Run the desktop UI with `--print-logs` to mirror firmware output to stdout while keeping the in-app log pane.
- The desktop log pane filters between `LOG` entries and aggregate `EVENTS` (state/info/warn/err); log-level controls remain visible when viewing `ALL` or `LOG`.
- Log entries are rendered with timestamp/level/logger columns and color-coded severities for quick scanning; export/console output uses the same formatted text.

---

## Development Notes

- The repo targets CircuitPython. The `lib/` folder includes frozen dependencies (`adafruit_ble`, `adafruit_hid`, etc.).
- Desktop tooling depends on PySide6 (Qt for Python).
- Use `python -m py_compile ...` for quick syntax validation; run `python tools/virtual_controller.py --port <serial>` for the UI.
- When sending logs from the host, keep messages single-line (newlines are escaped as `\\n` by the UI before sending).

---

## Contributing

1. Ensure you have the required Python environment (PySide6 for the UI, CircuitPython SDK for firmware deployment).
2. Update or add unit tests if making substantial changes.
3. Keep modules focused: logging stays in `firmware_logging`, hardware access in managers, UI-specific tweaks in `tools/`.
4. Submit PRs with clear descriptions and testing notes.
