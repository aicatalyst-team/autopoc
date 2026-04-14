"""Tests for the script execution tool."""

import os
import stat
import textwrap

import pytest

from autopoc.tools.script_tools import run_script


class TestRunScript:
    def test_successful_script_execution(self, tmp_path):
        """Test running a script that succeeds."""
        script = tmp_path / "test.py"
        script.write_text('print("hello world")')

        result = run_script.invoke(
            {
                "script_path": str(script),
                "timeout": 30,
            }
        )

        assert "EXIT_CODE: 0" in result
        assert "hello world" in result

    def test_script_with_nonzero_exit(self, tmp_path):
        """Test running a script that fails."""
        script = tmp_path / "fail.py"
        script.write_text("import sys; sys.exit(1)")

        result = run_script.invoke(
            {
                "script_path": str(script),
                "timeout": 30,
            }
        )

        assert "EXIT_CODE: 1" in result

    def test_script_with_stderr(self, tmp_path):
        """Test running a script that writes to stderr."""
        script = tmp_path / "stderr.py"
        script.write_text('import sys; print("error msg", file=sys.stderr)')

        result = run_script.invoke(
            {
                "script_path": str(script),
                "timeout": 30,
            }
        )

        assert "EXIT_CODE: 0" in result
        assert "error msg" in result
        assert "STDERR:" in result

    def test_script_not_found(self):
        """Test with a non-existent script."""
        result = run_script.invoke(
            {
                "script_path": "/nonexistent/script.py",
                "timeout": 30,
            }
        )

        assert "ERROR: Script not found" in result

    def test_not_a_python_script(self, tmp_path):
        """Test with a non-.py file."""
        script = tmp_path / "test.sh"
        script.write_text("echo hello")

        result = run_script.invoke(
            {
                "script_path": str(script),
                "timeout": 30,
            }
        )

        assert "ERROR: Not a Python script" in result

    def test_script_timeout(self, tmp_path):
        """Test script that exceeds timeout."""
        script = tmp_path / "slow.py"
        script.write_text("import time; time.sleep(60)")

        result = run_script.invoke(
            {
                "script_path": str(script),
                "timeout": 1,  # 1 second timeout
            }
        )

        assert "timed out" in result
        assert "EXIT_CODE: -1" in result

    def test_script_with_args(self, tmp_path):
        """Test passing arguments to script."""
        script = tmp_path / "args.py"
        script.write_text(
            textwrap.dedent("""\
            import sys
            print(f"args: {sys.argv[1:]}")
        """)
        )

        result = run_script.invoke(
            {
                "script_path": str(script),
                "timeout": 30,
                "script_args": "arg1 arg2",
            }
        )

        assert "EXIT_CODE: 0" in result
        assert "arg1" in result
        assert "arg2" in result

    def test_script_json_output(self, tmp_path):
        """Test script that produces JSON output (like PoC test scripts)."""
        script = tmp_path / "json_out.py"
        script.write_text(
            textwrap.dedent("""\
            import json
            results = [
                {"scenario_name": "health", "status": "pass", "duration_seconds": 0.5},
                {"scenario_name": "api", "status": "fail", "duration_seconds": 1.0},
            ]
            print(json.dumps({"results": results}))
        """)
        )

        result = run_script.invoke(
            {
                "script_path": str(script),
                "timeout": 30,
            }
        )

        assert "EXIT_CODE: 0" in result
        assert '"scenario_name"' in result
        assert '"status"' in result

    def test_not_a_file(self, tmp_path):
        """Test with a directory path."""
        result = run_script.invoke(
            {
                "script_path": str(tmp_path),
                "timeout": 30,
            }
        )

        assert "ERROR" in result
