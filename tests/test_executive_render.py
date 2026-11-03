"""The offline wrapper publishes packages only from verified reviewed inputs."""

import argparse
import hashlib
import json
import subprocess
import time
import zipfile
from pathlib import Path

import pytest

from autopoc import executive_render
from autopoc.executive_inputs import seal_inputs
from tests.test_executive_inputs import inputs


def sealed(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    evidence, narrative, review = inputs(run)
    return seal_inputs(
        evidence,
        narrative,
        review,
        tmp_path / "sealed",
        renderer_image="quay.io/org/image@sha256:" + "b" * 64,
    )


@pytest.fixture
def engine(monkeypatch, tmp_path):
    root = tmp_path / "renderer"
    root.mkdir()
    (root / "render.mjs").write_text("// trusted renderer")
    (root / "package.json").write_text('{"version":"1.0.0"}')
    monkeypatch.setenv("AUTOPOC_RENDERER_ROOT", str(root))

    def fake(command, **kwargs):
        assert command[:2] == ["node", str(root / "render.mjs")]
        assert 0 < kwargs["timeout"] <= 600
        data, output = map(Path, command[2:])
        assert sorted(p.name for p in data.iterdir()) == ["narrative.json", "scenes.json"]
        assert data.stat().st_mode & 0o077 == 0
        source = output / "source"
        (source / "dist").mkdir(parents=True)
        (source / "components").mkdir()
        (source / "components" / "ExecutiveSlide.vue").write_text("trusted component")
        (source / "slides.md").write_text("<ExecutiveSlide />")
        (source / "package-lock.json").write_text("{}")
        (source / "dist" / "index.html").write_text("<html>static presentation</html>")
        (source / "node_modules").symlink_to(root, target_is_directory=True)
        (output / "capture").mkdir()
        (output / "capture" / "private.webm").write_bytes(b"raw")
        (output / "executive-summary.pdf").write_bytes(b"%PDF-1.7 test")
        (output / "executive-summary.mp4").write_bytes(b"video")
        (output / "presentation-manifest.json").write_text(
            json.dumps(
                {
                    "status": "generated_unpublished",
                    "scenes": [{"id": "purpose"}],
                    "artifacts": {
                        "deck": {"status": "validated", "path": "source/dist"},
                        "pdf": {"status": "validated", "path": "executive-summary.pdf"},
                        "video": {"status": "validated", "path": "executive-summary.mp4"},
                    },
                }
            )
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(executive_render, "_run_renderer", fake)
    return fake


def test_packages_recovery_hashes_summary_and_reuse(tmp_path, engine, monkeypatch):
    package = sealed(tmp_path)
    output = tmp_path / "output"
    result = executive_render.render_executive(package, output)
    assert result["status"] == "generated_unpublished"
    assert result["input_sha256"] == hashlib.sha256(package.read_bytes()).hexdigest()
    assert result["evidence_sha256"]
    assert result["versions"]["image"].endswith("b" * 64)
    for metadata in result["artifacts"].values():
        assert metadata["status"] == "generated_unpublished"
        raw = (output / metadata["path"]).read_bytes()
        assert metadata["sha256"] == hashlib.sha256(raw).hexdigest()
        assert metadata["size"] == len(raw)
    with zipfile.ZipFile(output / "executable-source.zip") as source:
        assert {
            "render-inputs.zip",
            "recovery.json",
            "slides.md",
            "render.mjs",
            "package-lock.json",
            "components/ExecutiveSlide.vue",
        } <= set(source.namelist())
        assert source.read("render-inputs.zip") == package.read_bytes()
        assert not any(
            "node_modules" in p or "capture" in p or "dist/" in p for p in source.namelist()
        )
    with zipfile.ZipFile(output / "static-site.zip") as site:
        assert site.namelist() == ["index.html"]
    summary = (output / "executive-summary.md").read_text()
    for title in executive_render.TOPIC_TITLES.values():
        assert title in summary
    assert "report.md" in summary and "Smoke checks only" in summary
    monkeypatch.setattr(
        executive_render,
        "_run_renderer",
        lambda *a, **kw: pytest.fail("completed render repeated"),
    )
    assert executive_render.render_executive(package, output) == result
    (output / "executive-summary.pdf").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="conflict|integrity"):
        executive_render.render_executive(package, output)


def test_invalid_input_and_conflicting_or_symlink_output_blocked(tmp_path, engine):
    invalid = tmp_path / "invalid.zip"
    invalid.write_bytes(b"invalid")
    with pytest.raises(ValueError):
        executive_render.render_executive(invalid, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    package = sealed(tmp_path)
    conflict = tmp_path / "conflict"
    conflict.mkdir()
    (conflict / "existing").write_text("preserve")
    link = tmp_path / "link"
    link.symlink_to(conflict, target_is_directory=True)
    for output in (conflict, link, link / "nested"):
        with pytest.raises(ValueError):
            executive_render.render_executive(package, output)
    assert (conflict / "existing").read_text() == "preserve"


def test_video_failure_preserves_pdf_and_source(tmp_path, engine, monkeypatch):
    def failing(command, **kwargs):
        engine(command, **kwargs)
        output = Path(command[3])
        (output / "executive-summary.mp4").unlink()
        manifest = json.loads((output / "presentation-manifest.json").read_text())
        manifest["status"] = "partial"
        manifest["artifacts"]["video"] = {"status": "failed"}
        (output / "presentation-manifest.json").write_text(json.dumps(manifest))
        return subprocess.CompletedProcess(command, 1)

    monkeypatch.setattr(executive_render, "_run_renderer", failing)
    output = tmp_path / "output"
    result = executive_render.render_executive(sealed(tmp_path), output)
    assert result["status"] == "partial"
    assert result["artifacts"]["video"]["status"] == "failed"
    assert result["artifacts"]["pdf"]["status"] == "generated_unpublished"
    assert (output / "executable-source.zip").is_file()
    assert "Video generation failed" in (output / "executive-summary.md").read_text()


def test_cli_registration(tmp_path, engine, capsys):
    parser = argparse.ArgumentParser()
    executive_render.register_cli(parser.add_subparsers())
    args = parser.parse_args(
        [
            "executive-render",
            "--inputs",
            str(sealed(tmp_path)),
            "--output-dir",
            str(tmp_path / "output"),
        ]
    )
    args.func(args)
    assert json.loads(capsys.readouterr().out)["status"] == "generated_unpublished"


def test_local_cli_requires_output_directory():
    parser = argparse.ArgumentParser()
    executive_render.register_cli(parser.add_subparsers())
    args = parser.parse_args(["executive-render", "--inputs", "input.zip"])
    with pytest.raises(ValueError, match="output-dir"):
        args.func(args)


def test_resume_rejects_missing_artifact_metadata(tmp_path, engine):
    package = sealed(tmp_path)
    output = tmp_path / "output"
    executive_render.render_executive(package, output)
    path = output / "presentation-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["artifacts"] = {}
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="conflict|integrity"):
        executive_render.render_executive(package, output)


def test_engine_timeout_retains_independently_completed_artifacts(tmp_path, engine, monkeypatch):
    def timeout(command, **kwargs):
        engine(command, **kwargs)
        output = Path(command[3])
        (output / "executive-summary.mp4").unlink()
        manifest = json.loads((output / "presentation-manifest.json").read_text())
        manifest["artifacts"].pop("video")
        (output / "presentation-manifest.json").write_text(json.dumps(manifest))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(executive_render, "_run_renderer", timeout)
    output = tmp_path / "output"
    manifest = executive_render.render_executive(sealed(tmp_path), output, timeout=1)
    assert manifest["status"] == "partial"
    assert (output / "executive-summary.pdf").read_bytes().startswith(b"%PDF")
    assert manifest["artifacts"]["video"]["status"] == "failed"


def test_renderer_timeout_kills_child_processes(tmp_path):
    pid_path = tmp_path / "child.pid"
    executive_render._run_renderer(
        ["sh", "-c", 'sleep 60 & printf "%s" "$!" > "$1"; wait', "sh", str(pid_path)],
        timeout=1,
    )
    pid = int(pid_path.read_text())
    status = Path(f"/proc/{pid}/stat")
    # A killed child may briefly remain a zombie while the container init reaps it.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            if status.read_text().split()[2] == "Z":
                return
        except (FileNotFoundError, ProcessLookupError):
            return
        time.sleep(0.01)
    pytest.fail("Renderer child remained running after the process-group timeout")


def test_partial_cli_exits_unsuccessfully_with_result_receipt(monkeypatch, capsys):
    monkeypatch.setattr(executive_render, "render_executive", lambda *a: {"status": "partial"})
    args = argparse.Namespace(inputs="input.zip", output_dir="output")
    with pytest.raises(SystemExit) as raised:
        executive_render.cmd_executive_render(args)
    assert raised.value.code == 1
    assert json.loads(capsys.readouterr().out)["status"] == "partial"


def test_renderer_diagnostics_are_private(tmp_path):
    log = tmp_path / "renderer.log"
    executive_render._run_renderer(
        ["sh", "-c", "printf stdout; printf stderr >&2"], timeout=1, log_path=log
    )
    assert log.read_text() == "stdoutstderr"
    assert log.stat().st_mode & 0o777 == 0o600


def test_runtime_metrics_count_scratch_without_following_symlinks(tmp_path):
    import time

    scratch = tmp_path / "scratch"
    scratch.mkdir()
    (scratch / "content").write_bytes(b"12345")
    outside = tmp_path / "outside"
    outside.write_bytes(b"not scratch")
    (scratch / "link").symlink_to(outside)
    (scratch / "directory-link").symlink_to(tmp_path, target_is_directory=True)
    peak = tmp_path / "memory.peak"
    peak.write_text("123456")
    result = executive_render._runtime_metrics(time.monotonic(), [scratch, scratch], peak)
    assert result["scratch_usage_bytes"] == 5
    assert result["peak_memory_bytes"] == 123456
    assert result["elapsed_seconds"] >= 0
    peak.unlink()
    assert (
        executive_render._runtime_metrics(time.monotonic(), [scratch], peak)["peak_memory_bytes"]
        is None
    )
    assert (
        executive_render._runtime_metrics(time.monotonic(), [tmp_path / "missing"], peak)[
            "scratch_usage_bytes"
        ]
        is None
    )
