"""Advertised worker executable dispatches the checkout's actual CLI module."""

import os
import subprocess
from pathlib import Path


def test_worker_executable_dispatches_visuals_help():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [str(root / "scripts/autopoc-tools"), "executive-visuals", "--help"],
        env={**os.environ, "PYTHONPATH": str(root / "src")},
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    assert "--manifest" in result.stdout and "--output" in result.stdout
