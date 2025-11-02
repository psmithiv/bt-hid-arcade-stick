# Bluetooth HID Arcade Stick — Codebase Analysis Report

Date: 2025-10-31

This report summarizes the current repository, inferred requirements, and suggestions for improvement based on a read‑only analysis of the codebase. No functional changes were made.

## Summary

CircuitPython firmware plus desktop tooling for a Bluetooth/USB arcade stick:

- Firmware maps GPIO inputs to HID (BLE + USB), with debouncing and a modern gamepad report (16 buttons, hat switch, X/Y axes).
- BLE stack handles advertising, pairing (including long‑press pairing button), reconnection, and emits lifecycle events.
- A serial debug interface mirrors state/logs and accepts virtual button commands from a desktop “Virtual Controller” UI built with PySide6.
- Sphinx documentation and basic unit tests are included; a deploy script targets a CIRCUITPY volume.

## Repository Layout and Responsibilities

- `code.py` — Firmware entrypoint. Wires managers (BLE, USB, inputs, power, debug) and runs the cooperative loop.
- `config.py` — Central configuration: button order, pin map, debounce, BLE/USB/debug settings, log level.
- `input_manager.py` — Active‑low GPIO polling with debounce; returns `InputEvents(pressed, released)`.
- `hid_controller.py` — Maintains active buttons, computes hat/axes from D‑pad, builds 16‑button mask, and sends reports over BLE/USB. Notifies observers of state changes.
- `hid_report.py` — Shared HID descriptor and constants. Report ID 0x01; 16 buttons + hat + 2 axes; total 6 bytes.
- `ble_manager.py` — Initializes BLE radio + HID service + device info; manages advertising, pairing mode (with hold‑time and timeout), bond detection, and connection lifecycle; publishes events to listeners.
- `usb_hid_manager.py` — Debug stub for USB HID mirroring; records last report and logs when enabled.
- `debug_interface.py` — Serial protocol: READY handshake, periodic state mirroring (deduped), command handling (`PRESS`, `RELEASE`, `STATE?`, `PAIR`, `LOG`), and BLE event forwarding. Robust serial flush fallback.
- `power_manager.py` — Placeholder; future telemetry/sleep hooks.
- `sd/boot.py` — CircuitPython boot customizer: sets USB identification strings and enables a single HID gamepad interface using the shared descriptor.
- `tools/virtual_controller.py` — PySide6 desktop UI: button grid (D‑pad, face, system), serial bridge in a background thread, BLE status, log viewer with category/level filters, search, save/clear.
- `tools/host_test.py` — HID listener that ensures `hidapi` is preloaded; reads reports from a connected device.
- `tools/dump_hid_descriptor.py` — macOS helper to extract HID report descriptors via `ioreg`.
- `docs/` — Sphinx site (overview, hardware wiring, API reference); GH Actions job builds docs.
- `scripts/deploy.py` — Copies selected files to a mounted CIRCUITPY volume; removes known conflicts; optional `sd/boot.py` copy.
- `tests/` — Unit tests with stubs for CircuitPython modules; cover HID mapping and minimal input polling behaviors.

## Runtime Behavior

Main loop (`code.py`):

- Initializes BLE (name, HID service, device info, ads/scan response), USB HID manager, input manager, HID controller, power manager, and debug interface.
- Iterates: `ble_manager.poll()`, `power_manager.poll()`, `debug_interface.poll()`, `events = input_manager.poll()`, then `hid_controller.process_inputs(events)` when changes occur; sleeps 10ms.

HID mapping (`hid_controller.py` + `hid_report.py`):

- Button order defined by `config.HID_BUTTONS` (16 entries, including D‑pad and a virtual "PAIRING" slot to keep the count constant).
- Reports include: Report ID (0x01), 16‑bit button mask, 4‑bit hat (with null state), 4‑bit padding nibble (0xF), and signed 8‑bit X/Y axes.
- D‑pad contributes to both hat and axes; opposing directions cancel; axes clamp to ±127.
- Duplicate reports are suppressed; state callback can be registered (used by debug interface for STATE messages).

BLE lifecycle (`ble_manager.py`):

- Creates `BLERadio`, HID service (uses custom descriptor when supported), and `DeviceInfoService`.
- Builds `ProvideServicesAdvertisement` with name/appearance; optional scan response.
- Detects existing bonds; advertises for reconnection if bonded, otherwise enters pairing mode automatically on cold start.
- Pairing mode can be triggered via virtual "PAIRING" or a dedicated hardware pin (active‑low, long‑press detection); exits on timeout.
- Emits structured events (`initialized`, `advertising`, `connected`, `disconnected`, `pairing_active`, `pairing_timeout`, `disabled`, `advertising_error`) for the debug interface to present.
- Defensive logging and diagnostics payloads make field issues observable.

Debugging & logs (`debug_interface.py`, `firmware_logging.py`, UI):

- Firmware logs: JSON with `type: "log"` and `level/logger/message/timestamp`.
- Debug messages: `type = state | ready | info | warn | err` plus BLE `source` tagging.
- Serial transport quirks (USB CDC flush errors) are handled with a raw write fallback.
- UI shows categories (ALL/LOG/RAW), level filtering for LOG, BLE status, and supports search and saving log text.

USB HID (`usb_hid_manager.py`):

- Stub captures mirrored reports for diagnostics/tests. Actual HID device configuration is established in `sd/boot.py` at boot.

## Configuration Model (`config.py`)

- Buttons: `INPUT_BUTTONS` and `HID_BUTTONS` define the polled and reported order, respectively.
- D‑pad defaults (names, axis ranges, hat neutral) inform HID computations.
- Pin map uses string names resolved via `board` (active‑low with pull‑ups). Pairing button pin optional.
- Debounce window (`DEBOUNCE_MS`) and pairing hold/timeout values are centralized.
- BLE, HID (USB enabled flag), debug (virtual buttons), power, and log level are aggregated in `CONTROLLER_CONFIG`.

## Documentation and CI

- Sphinx site: overview, hardware wiring, and autodoc API reference. `docs/conf.py` mocks hardware‑specific imports and adds standard doc extensions.
- CI (`.github/workflows/docs.yml`): builds the Sphinx site on pushes to `development` and uploads artifacts.

## Tests

- `tests/conftest.py` stubs `board`, `digitalio`, `usb_hid`, `supervisor`, `adafruit_hid.find_device`, and core BLE classes to allow host‑side testing.
- `tests/test_hid_controller.py` validates: button mask mapping (including high/low byte boundaries), hat/axes from D‑pad, report packing (length, report ID, hat nibble), and state callback behavior.
- `tests/test_input_manager.py` sanity checks `InputManager.poll()` shape with stubs; room to expand.

## Inferred Requirements

Functional:

- Expose the device to hosts as a modern HID gamepad (16 buttons, hat switch, X/Y axes) over USB and BLE.
- Debounce active‑low GPIO inputs and maintain consistent logical button ordering between hardware and HID reports.
- Provide a reliable BLE pairing flow driven by hardware long‑press or host command; support bond detection and reconnection.
- Mirror controller state and logs over serial in a structured format for host tooling; accept virtual button commands for testing.
- Offer a desktop UI to drive virtual inputs, view logs, monitor BLE status, and save sessions.

Non‑functional:

- Modular separation: input, HID, BLE, debug, logging, and power concerns are isolated.
- Robustness in constrained environments: tolerate missing APIs, serial transport quirks, and older library versions.
- Developer ergonomics: docs, deployment helper, unit tests, and host utilities.

Roadmap cues (from README and code):

- Validate BLE HID end‑to‑end; finalize production pin mapping; expand tests; add power management and macro/customization features; consider packaging for distribution.

## Strengths Observed

- Clear module boundaries with well‑named loggers and docstrings.
- HID report design aligns with mainstream host expectations; boot customization avoids extraneous boot interfaces.
- Thoughtful robustness: fallbacks for older libraries, serial flush errors, adapter capability differences, and event diagnostics.
- Developer tooling: virtual controller UI with category/level filtering, search and save; deploy/docs scripts and CI for docs.

## Suggestions and Improvements

Testing and CI:

- Add CI job to run unit tests (in addition to doc builds). Include `pytest -q` with the existing stubs.
- Extend test coverage:
  - `ble_manager.py`: advertising start/stop paths, pairing timeout, event emission, bond detection behavior using stubs.
  - `debug_interface.py`: command parsing (`PRESS`/`RELEASE`/`PAIR`/`LOG`), READY/STATE flow, dedup logic, BLE event forwarding.
  - `input_manager.py`: explicit debounce edge cases and pin resolution failures.

Firmware structure and resiliency:

- Consider reading overrides from `settings.toml` for device name, log level, debounce, and pin map to reduce rebuilds for hardware tweaks.
- Guard imports that are only needed at runtime to further ease host‑side analysis; most hotspots already defer (e.g., `usb_hid` in creators), but `ble_manager.py` imports hardware libs at module scope—fine with test/doc mocks but worth noting.
- Expose a lightweight health/status snapshot endpoint via the debug interface (e.g., `STATUS?`) that returns BLE/USB state and config summary.
- Optionally serialize state changes at a fixed rate (e.g., 30 Hz) to cap log volume when buttons chatter; current dedup helps but a rate cap can aid host UIs.

Configuration and HID:

- Surface `hat_neutral` in `CONTROLLER_CONFIG` (backed by `DPAD_DEFAULTS`) for explicitness.
- Provide an optional mapping profile layer (e.g., aliases/macros, remaps) with a safe default; keep 16‑button shape constant.
- Document the rationale for mirroring D‑pad to both hat and axes (compat benefits), with a toggle to disable axes mirroring if a host misinterprets inputs.

BLE lifecycle:

- Add an explicit “pairing canceled” path if pairing is started by mistake (e.g., release press within a grace period).
- Persist pairing/bonding state observations via the debug channel to help testers understand reconnection flows.
- Optionally expose manufacturer, appearance and software revision in `config.py` (already supported in `ble_manager`, just surface in config defaults/docs).

Debug interface and desktop UI:

- UI enhancements:
  - Port picker and reconnect button; dynamic port list refresh.
  - Dedicated controls for `PAIR` and `STATE?`, and a small console to send arbitrary commands.
  - Option to export logs as JSON in addition to plain text.
  - Optional timestamps in the log pane with user‑visible toggle.
- Add a “log level” control in the UI that sends `LOG <LEVEL> firmware_logging <message>` or a dedicated `SET LOGLEVEL` command implemented in firmware.

Docs and developer experience:

- Add a short “Getting Started” doc covering environment setup (PySide6, PySerial), deployment, and running the UI, with troubleshooting for macOS serial permissions.
- Expand hardware wiring table with concrete production pinouts; link to a simple loopback/LED test for validating each input.
- Pin library versions or include a minimal `requirements.txt` for the host tools (`PySide6`, `pyserial`, optional `hidapi`).

Packaging and distribution:

- Optional: create a minimal Python package for the host UI (`pip install .[ui]`) with entry‑point `arcadectl` to launch `tools/virtual_controller.py`.
- Consider freezing critical libs into `lib/` on the device for stability.

Performance/footprint:

- The main loop’s 10ms sleep looks reasonable; if BLE event latency becomes a concern, consider tracking elapsed time and adapting the poll cadence.

## Risks and Edge Cases

- BLE adapter differences: the code guards appearance/name setting and bond APIs, but some boards may still behave differently; the diagnostics/logs will help.
- HID descriptor compatibility: older `HIDService` may ignore custom descriptors (handled); keep `boot.py` source of truth and ensure firmware matches it.
- Serial transport: the flush workaround is implemented; heavy logging can still saturate CDC; consider rate limiting for long sessions.

## Quick Wins

- Add a tests CI job and a `requirements.txt` for host tooling.
- Add `STATUS?` and `SET LOGLEVEL <LEVEL>` to the debug interface.
- Expose `hat_neutral` in the config and document it in the hardware/API docs.
- UI port picker and reconnect button to improve usability without CLI flags.

## Overall Assessment

The codebase is clean, modular, and thoughtfully designed for embedded constraints and developer tooling. It already includes the right scaffolding (docs, deploy script, tests, UI). The next high‑value steps are validating the BLE path on target hardware, tightening tests around BLE/debug flows, and adding small UX improvements to the desktop UI and debug protocol.

