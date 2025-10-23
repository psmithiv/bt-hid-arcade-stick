#!/usr/bin/env python3
"""
CI helper for building Sphinx documentation.

Runs ``sphinx-build`` with warnings treated as errors so regressions in
docstrings or rst sources cause the job to fail. The script lives alongside
the deployment helper to make it easy to invoke from continuous-integration
pipelines or local pre-flight checks.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Build the Sphinx documentation with strict settings."""
    project_root = Path(__file__).resolve().parents[1]
    docs_dir = project_root / "docs"
    html_dir = project_root / "build" / "html"
    html_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "sphinx",
        "-W",  # treat warnings as errors
        "--keep-going",
        "-b",
        "html",
        str(docs_dir),
        str(html_dir),
    ]

    env = os.environ.copy()
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=project_root, env=env, check=False)
    if result.returncode != 0:
        print("Sphinx build failed.", file=sys.stderr)
    else:
        print(f"Sphinx HTML output available at {html_dir}")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
