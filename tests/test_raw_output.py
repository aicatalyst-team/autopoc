"""Tests for raw test output capture, truncation, and log formatting."""

import textwrap
from pathlib import Path

import pytest

from autopoc.agents.poc_execute import _write_raw_test_output
from autopoc.state import PoCResult
from autopoc.tools.script_tools import (
    MAX_SCENARIO_OUTPUT_BYTES,
    RawRunRecord,
    clear_raw_run_log,
    get_raw_run_log,
    run_script,
    truncate_output,
)


@pytest.fixture(autouse=True)
def _isolate_raw_log():
    """Ensure the module-level buffer is clean before and after each test."""
    clear_raw_run_log()
    yield
    clear_raw_run_log()


# ---------------------------------------------------------------------------
# RawRunRecord capture
# ---------------------------------------------------------------------------


class TestRawRunRecordCapture:
    def test_run_script_captures_raw_output(self, tmp_path):
        """run_script populates _raw_run_log with full untruncated output."""
        script = tmp_path / "hello.py"
        script.write_text(
            textwrap.dedent("""\
                import sys
                print("hello stdout")
                print("hello stderr", file=sys.stderr)
            """)
        )

        result = run_script.invoke({"script_path": str(script)})

        # The LLM-facing return value should still contain the output
        assert "hello stdout" in result
        assert "hello stderr" in result

        log = get_raw_run_log()
        assert len(log) == 1

        record = log[0]
        assert record.script_path == str(script)
        assert "hello stdout" in record.stdout_raw
        assert "hello stderr" in record.stderr_raw
        assert record.exit_code == 0
        assert record.duration_seconds >= 0
        assert record.timed_out is False

    def test_buffer_cleared_after_get(self, tmp_path):
        """get_raw_run_log returns the buffer and clears it."""
        script = tmp_path / "noop.py"
        script.write_text("pass\n")

        run_script.invoke({"script_path": str(script)})

        first = get_raw_run_log()
        assert len(first) == 1

        second = get_raw_run_log()
        assert len(second) == 0

    def test_multiple_invocations_captured(self, tmp_path):
        """Multiple run_script calls append to the buffer."""
        script = tmp_path / "counter.py"
        script.write_text("print('run')\n")

        run_script.invoke({"script_path": str(script)})
        run_script.invoke({"script_path": str(script)})

        log = get_raw_run_log()
        assert len(log) == 2

    def test_empty_output_captured(self, tmp_path):
        """A script that produces no output still records a RawRunRecord."""
        script = tmp_path / "silent.py"
        script.write_text("pass\n")

        run_script.invoke({"script_path": str(script)})

        log = get_raw_run_log()
        assert len(log) == 1
        assert log[0].stdout_raw == ""
        assert log[0].stderr_raw == ""
        assert log[0].exit_code == 0

    def test_timeout_captured(self, tmp_path):
        """A timed-out script produces a record with timed_out=True."""
        script = tmp_path / "hang.py"
        script.write_text("import time; time.sleep(60)\n")

        result = run_script.invoke(
            {"script_path": str(script), "timeout": 1}
        )
        assert "timed out" in result.lower()

        log = get_raw_run_log()
        assert len(log) == 1
        assert log[0].timed_out is True
        assert log[0].exit_code == -1

    def test_nonzero_exit_code(self, tmp_path):
        """A failing script records the actual exit code."""
        script = tmp_path / "fail.py"
        script.write_text("import sys; sys.exit(42)\n")

        run_script.invoke({"script_path": str(script)})

        log = get_raw_run_log()
        assert len(log) == 1
        assert log[0].exit_code == 42

    def test_large_output_not_truncated_in_buffer(self, tmp_path):
        """Raw buffer stores the full output, even if >20K chars."""
        script = tmp_path / "big.py"
        # Generate 30K chars of output
        script.write_text("print('x' * 30000)\n")

        result = run_script.invoke({"script_path": str(script)})

        # The LLM-facing return should be truncated
        assert "truncated" in result

        # But the raw buffer should have the full output
        log = get_raw_run_log()
        assert len(log) == 1
        assert len(log[0].stdout_raw) == 30001  # 30000 x's + newline

    def test_validation_errors_not_captured(self):
        """Invalid paths don't produce RawRunRecords (no subprocess ran)."""
        run_script.invoke({"script_path": "/nonexistent/path.py"})

        log = get_raw_run_log()
        assert len(log) == 0


# ---------------------------------------------------------------------------
# Truncation utility
# ---------------------------------------------------------------------------


class TestTruncateOutput:
    def test_small_input_passes_through(self):
        text = "hello world"
        assert truncate_output(text) == text

    def test_exact_limit_passes_through(self):
        text = "x" * MAX_SCENARIO_OUTPUT_BYTES
        assert truncate_output(text) == text

    def test_large_input_truncated(self):
        text = "x" * (MAX_SCENARIO_OUTPUT_BYTES * 2)
        result = truncate_output(text)

        assert "truncated" in result
        assert "showing last 100KB" in result
        assert "200KB total" in result
        # The tail should be preserved
        assert result.endswith("x" * 100)

    def test_tail_preserved(self):
        """Truncation keeps the END of the text, not the beginning."""
        text = "A" * MAX_SCENARIO_OUTPUT_BYTES + "ENDMARKER"
        result = truncate_output(text)

        assert "truncated" in result
        assert result.endswith("ENDMARKER")

    def test_utf8_boundary_safe(self):
        """Multi-byte UTF-8 chars at the truncation boundary are handled."""
        # Each emoji is 4 bytes. Fill beyond the limit with emojis.
        emoji_count = (MAX_SCENARIO_OUTPUT_BYTES // 4) + 100
        text = "\U0001f600" * emoji_count  # grinning face

        result = truncate_output(text)

        assert "truncated" in result
        # Must be valid UTF-8 — no decode errors
        result.encode("utf-8")

    def test_custom_limit(self):
        text = "x" * 200
        result = truncate_output(text, max_bytes=50)

        assert "truncated" in result
        assert len(result.encode("utf-8")) < 200

    def test_empty_string(self):
        assert truncate_output("") == ""


# ---------------------------------------------------------------------------
# Log file formatting (_write_raw_test_output)
# ---------------------------------------------------------------------------


class TestWriteRawTestOutput:
    def test_writes_log_file(self, tmp_path):
        """Basic test that log file is written with correct structure."""
        clone_path = str(tmp_path)

        # Seed the raw log buffer directly (bypassing run_script)
        from autopoc.tools.script_tools import _raw_run_log

        _raw_run_log.append(
            RawRunRecord(
                script_path="/tmp/poc_test.py",
                timestamp="2025-04-29T10:15:00+00:00",
                stdout_raw='{"results": [{"scenario_name": "health", "status": "pass"}]}',
                stderr_raw="some warnings here",
                exit_code=0,
                duration_seconds=1.5,
            )
        )

        poc_results = [
            PoCResult(
                scenario_name="health",
                status="pass",
                output="OK",
                duration_seconds=1.5,
            )
        ]

        result = _write_raw_test_output(clone_path, "test-project", poc_results)

        assert result is not None
        log_path = Path(result) / "test-run.log"
        assert log_path.exists()

        content = log_path.read_text()
        assert "AutoPoC Test Run — test-project" in content
        assert "RUN #1:" in content
        assert "--- STDOUT ---" in content
        assert "--- STDERR ---" in content
        assert "some warnings here" in content
        assert "PARSED RESULTS SUMMARY" in content
        assert "[PASS ]" in content
        assert "health" in content

    def test_copies_test_script(self, tmp_path):
        """poc_test.py is copied to poc-test-output/."""
        clone_path = str(tmp_path)
        (tmp_path / "poc_test.py").write_text("# test script\nprint('hello')\n")

        from autopoc.tools.script_tools import _raw_run_log

        _raw_run_log.append(
            RawRunRecord(
                script_path=str(tmp_path / "poc_test.py"),
                timestamp="2025-04-29T10:15:00+00:00",
                stdout_raw="output",
                stderr_raw="",
                exit_code=0,
                duration_seconds=0.5,
            )
        )

        result = _write_raw_test_output(clone_path, "proj", [])

        assert result is not None
        copied = Path(result) / "poc_test.py"
        assert copied.exists()
        assert "# test script" in copied.read_text()

    def test_returns_none_when_no_raw_log(self, tmp_path):
        """Returns None if no run_script calls were captured."""
        result = _write_raw_test_output(str(tmp_path), "proj", [])
        assert result is None

    def test_multiple_runs_formatted(self, tmp_path):
        """Multiple run_script invocations produce separate sections."""
        from autopoc.tools.script_tools import _raw_run_log

        _raw_run_log.append(
            RawRunRecord(
                script_path="/tmp/poc_test.py",
                timestamp="2025-04-29T10:15:00+00:00",
                stdout_raw="first run output",
                stderr_raw="",
                exit_code=1,
                duration_seconds=5.0,
            )
        )
        _raw_run_log.append(
            RawRunRecord(
                script_path="/tmp/poc_test.py",
                timestamp="2025-04-29T10:16:00+00:00",
                stdout_raw="second run output (after fix)",
                stderr_raw="",
                exit_code=0,
                duration_seconds=2.0,
            )
        )

        result = _write_raw_test_output(str(tmp_path), "proj", [])
        content = Path(result) / "test-run.log"
        text = content.read_text()

        assert "RUN #1:" in text
        assert "RUN #2:" in text
        assert "first run output" in text
        assert "second run output (after fix)" in text
        assert "Total run_script invocations: 2" in text

    def test_timed_out_run_formatted(self, tmp_path):
        """Timed-out runs show STATUS: TIMED OUT in the log."""
        from autopoc.tools.script_tools import _raw_run_log

        _raw_run_log.append(
            RawRunRecord(
                script_path="/tmp/poc_test.py",
                timestamp="2025-04-29T10:15:00+00:00",
                stdout_raw="",
                stderr_raw="",
                exit_code=-1,
                duration_seconds=300.0,
                timed_out=True,
            )
        )

        result = _write_raw_test_output(str(tmp_path), "proj", [])
        text = (Path(result) / "test-run.log").read_text()

        assert "STATUS: TIMED OUT" in text
        assert "EXIT CODE: -1" in text

    def test_truncation_applied_to_large_output(self, tmp_path):
        """Outputs over 100KB are tail-truncated in the log file."""
        from autopoc.tools.script_tools import _raw_run_log

        big_stdout = "x" * (MAX_SCENARIO_OUTPUT_BYTES * 2)
        _raw_run_log.append(
            RawRunRecord(
                script_path="/tmp/poc_test.py",
                timestamp="2025-04-29T10:15:00+00:00",
                stdout_raw=big_stdout,
                stderr_raw="small stderr",
                exit_code=0,
                duration_seconds=1.0,
            )
        )

        result = _write_raw_test_output(str(tmp_path), "proj", [])
        text = (Path(result) / "test-run.log").read_text()

        assert "truncated" in text
        # stderr should NOT be truncated
        assert "small stderr" in text

    def test_empty_results_shows_no_parsed(self, tmp_path):
        """When no results were parsed, summary says so."""
        from autopoc.tools.script_tools import _raw_run_log

        _raw_run_log.append(
            RawRunRecord(
                script_path="/tmp/poc_test.py",
                timestamp="2025-04-29T10:15:00+00:00",
                stdout_raw="garbage output",
                stderr_raw="",
                exit_code=1,
                duration_seconds=2.0,
            )
        )

        result = _write_raw_test_output(str(tmp_path), "proj", [])
        text = (Path(result) / "test-run.log").read_text()

        assert "No structured results were parsed" in text

    def test_error_messages_in_summary(self, tmp_path):
        """Error messages from PoCResult appear in the summary."""
        from autopoc.tools.script_tools import _raw_run_log

        _raw_run_log.append(
            RawRunRecord(
                script_path="/tmp/poc_test.py",
                timestamp="2025-04-29T10:15:00+00:00",
                stdout_raw="output",
                stderr_raw="",
                exit_code=1,
                duration_seconds=3.0,
            )
        )

        poc_results = [
            PoCResult(
                scenario_name="api-test",
                status="fail",
                output="",
                error_message="Connection refused",
                duration_seconds=3.0,
            )
        ]

        result = _write_raw_test_output(str(tmp_path), "proj", poc_results)
        text = (Path(result) / "test-run.log").read_text()

        assert "[FAIL ]" in text
        assert "api-test" in text
        assert "Connection refused" in text
