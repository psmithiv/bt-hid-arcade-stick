"""
Host-side helper to monitor HID reports coming from the arcade stick.

Robustly ensures the hidapi dynamic library is available before importing
the lightweight ``hid`` Python wrapper. Works on macOS with Conda/venv,
Python wheels, or Homebrew installs (Apple silicon or Intel).
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from pathlib import Path
from typing import Iterable

VENDOR_ID = 0x239A
PRODUCT_ID = 0x8026


def _iter_candidates() -> Iterable[Path | str]:
    """Yield likely paths/names for a hidapi dylib.

    Order of preference:
    1) Explicit env var `HIDAPI_LIBRARY`
    2) hidapi wheel-shipped dylibs (if package installed)
    3) Current env lib dir (Conda/venv): $PREFIX/lib/libhidapi*.dylib
    4) Homebrew (arm64 and Intel prefixes)
    5) Names from ``ctypes.util.find_library``
    """

    # 1) Explicit path via env var
    env_path = os.environ.get("HIDAPI_LIBRARY")
    if env_path:
        yield Path(env_path)

    # 2) Wheel-provided dylibs (package: hidapi)
    try:
        import hidapi  # type: ignore

        wheel_dir = Path(hidapi.__file__).resolve().parent
        for name in (
                "libhidapi.dylib",
                "libhidapi-iohidmanager.dylib",
                "libhidapi-libusb.dylib",
        ):
            candidate = wheel_dir / name
            if candidate.exists():
                yield candidate
    except Exception:
        pass

    # 3) Current Python environment prefix (Conda/venv)
    prefix = Path(sys.prefix)
    for name in (
            "libhidapi.dylib",
            "libhidapi-iohidmanager.dylib",
            "libhidapi-libusb.dylib",
    ):
        candidate = prefix / "lib" / name
        if candidate.exists():
            yield candidate

    # 4) Homebrew common prefixes (Apple silicon and Intel)
    for prefix in ("/opt/homebrew", "/usr/local"):
        candidate = Path(prefix) / "opt/hidapi/lib/libhidapi.dylib"
        if candidate.exists():
            yield candidate

    # 5) Names discoverable by the dynamic loader
    for name in ("hidapi", "hidapi-hidraw", "hidapi-libusb", "hidapi-iohidmanager"):
        lib_name = ctypes.util.find_library(name)
        if lib_name:
            # May be a bare soname; CDLL can still try to resolve it.
            yield lib_name


def _load_hidapi() -> None:
    """
    Ensure the hidapi shared library is available before importing ``hid``.

    Fast path: if importing ``hid`` and calling ``enumerate`` works, bail out.
    Otherwise, try loading a hidapi dylib from a set of candidate locations.
    """

    # Fast path: if the Python binding already works, don't preload anything.
    try:
        import hid  # type: ignore

        hid.enumerate()  # smoke test that the extension is usable
        return
    except Exception:
        pass

    load_errors: list[tuple[Path | str, BaseException]] = []

    for candidate in _iter_candidates():
        try:
            if not candidate:
                continue
            ctypes.CDLL(str(candidate))
            return
        except OSError as exc:  # pragma: no cover - diagnostic only
            load_errors.append((candidate, exc))

    # If we reach here, explain what we tried and how to fix.
    hints = [
        "Install hidapi (e.g. `pip install hidapi` or `conda install -c conda-forge hidapi`).",
        "If using Homebrew on Apple silicon, prefer /opt/homebrew (arm64).",
        "Set HIDAPI_LIBRARY to the full path of libhidapi.dylib if it resides elsewhere.",
    ]
    details = "\n".join(f"  - Tried '{path}': {err}" for path, err in load_errors)
    raise ImportError(f"Unable to load hidapi library.\n{details}\n" + "\n".join(hints))


def main() -> int:
    _load_hidapi()

    import hid  # type: ignore

    for dev in hid.enumerate():
        if dev.get("vendor_id") == VENDOR_ID and dev.get("product_id") == PRODUCT_ID:
            print(
                f"Listening on {dev.get('product_string')} "
                f"({dev.get('vendor_id'):04x}:{dev.get('product_id'):04x})"
            )
            try:
                controller = hid.device()
                # pyhidapi expects a bytes path; coerce if needed
                path = dev.get("path")
                if isinstance(path, str):
                    path = path.encode()
                try:
                    controller.open_path(path)
                except OSError as e1:
                    # Fallback: open by VID/PID (some macOS builds prefer this)
                    try:
                        controller.open(dev.get("vendor_id"), dev.get("product_id"))
                    except OSError as e2:
                        print("Failed to open HID device via path and VID/PID:\n"
                              f"  open_path error: {e1}\n  open(vid,pid) error: {e2}")
                        return 1

                try:
                    # Non-blocking loop with timeout-based reads to avoid hanging
                    controller.set_nonblocking(True)
                    while True:
                        # Read up to 64 bytes with a small timeout (ms)
                        data = controller.read(64, timeout_ms=200)
                        if data:
                            print(data)
                finally:
                    controller.close()
            except KeyboardInterrupt:
                print("\nStopped.")
            return 0

    print("No matching HID device found. Is the firmware running and connected via USB?")
    return 1


if __name__ == "__main__":
    sys.exit(main())