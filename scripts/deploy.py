#!/usr/bin/env python3
"""
Utility script for deploying the CircuitPython project to a mounted
CIRCUITPY drive.
"""

import argparse
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VOLUME = Path("/Volumes/CIRCUITPY")

# Explicit file list keeps deployment predictable; adjust as project grows.
FILES_TO_COPY = [
    "code.py",
    "config.py",
    "input_manager.py",
    "hid_controller.py",
    "ble_manager.py",
    "usb_hid_manager.py",
    "power_manager.py",
    "debug_interface.py",
    "firmware_logging.py",
]
DIRS_TO_COPY = [
    "lib",
]

EXTRA_FILES = [
    ("sd/boot.py", "boot.py"),
]

CONFLICTING_PATHS = [
    Path("log_utils.py"),
    Path("log_utils.mpy"),
]


def remove_conflicts(volume: Path):
    """Remove known conflicting files on the target volume."""
    for relative_path in CONFLICTING_PATHS:
        target = volume / relative_path
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
                print(f"Removed conflicting directory: {target}")
            else:
                target.unlink()
                print(f"Removed conflicting file: {target}")


def copy_item(src: Path, dst: Path):
    """Copy a file or directory from src to dst."""
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def deploy_project(volume: Path):
    """Copy project files to the mounted CIRCUITPY volume."""
    if not volume.exists():
        raise FileNotFoundError(f"Target volume not found: {volume}")

    remove_conflicts(volume)

    for relative_path in FILES_TO_COPY:
        src = PROJECT_ROOT / relative_path
        if not src.exists():
            print(f"Skipping missing file: {relative_path}")
            continue
        dst = volume / relative_path
        print(f"Copying {src} -> {dst}")
        copy_item(src, dst)

    for src_path, dest_path in EXTRA_FILES:
        src = PROJECT_ROOT / src_path
        if not src.exists():
            print(f"Skipping missing file: {src_path}")
            continue
        dst = volume / dest_path
        print(f"Copying {src} -> {dst}")
        copy_item(src, dst)

    for relative_path in DIRS_TO_COPY:
        src = PROJECT_ROOT / relative_path
        if not src.exists():
            print(f"Skipping missing directory: {relative_path}")
            continue
        dst = volume / relative_path
        print(f"Copying {src} -> {dst}")
        copy_item(src, dst)


def parse_args():
    parser = argparse.ArgumentParser(description="Deploy project to a CIRCUITPY volume.")
    parser.add_argument(
        "--volume",
        type=Path,
        default=DEFAULT_VOLUME,
        help=f"Path to CIRCUITPY volume (default: {DEFAULT_VOLUME})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        deploy_project(args.volume)
    except Exception as exc:  # pragma: no cover - deployment environment dependent
        print(f"Deployment failed: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
