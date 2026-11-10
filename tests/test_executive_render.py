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
        assert sorted(p.name for p in data.iterdir()) == [
            "narrative.json",
            "scenes.json",
            "versions.json",
        ]
        assert json.loads((data / "versions.json").read_text())["template"] == 2
        assert data.stat().st_mode & 0o077 == 0
        source = output / "source"
        (source / "dist").mkdir(parents=True)
        (source / "components").mkdir()
        (source / "components" / "ExecutiveSlide.vue").write_text("trusted component")
        for name in ("assets/redhat", "public/brand"):
            (source / name).mkdir(parents=True)
            (source / name / "font.woff2").write_bytes(b"local font")
            (source / name / "OFL.txt").write_text("font license")
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
        for name in ("assets/redhat", "public/brand"):
            assert source.read(f"{name}/font.woff2") == b"local font"
            assert source.read(f"{name}/OFL.txt") == b"font license"
        assert json.loads(source.read("versions.json"))["template"] == 2
        assert json.loads(source.read("recovery.json"))["template_version"] == 2
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


def test_legacy_inputs_need_their_original_pinned_renderer(tmp_path, monkeypatch):
    evidence, narrative, review = inputs(tmp_path)
    legacy = seal_inputs(
        evidence,
        narrative,
        review,
        tmp_path / "sealed",
        renderer_image="quay.io/org/legacy@sha256:" + "a" * 64,
        template_version=1,
    )
    monkeypatch.setattr(executive_render, "_run_renderer", lambda *a, **k: pytest.fail("launched"))
    with pytest.raises(ValueError, match="original.*renderer"):
        executive_render.render_executive(legacy, tmp_path / "output")


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


def test_content_failure_does_not_publish_the_unvalidated_static_deck(
    tmp_path, engine, monkeypatch
):
    def invalid(command, **kwargs):
        engine(command, **kwargs)
        output = Path(command[3])
        document = json.loads((output / "presentation-manifest.json").read_text())
        for kind in ("deck", "pdf", "video"):
            document["artifacts"][kind]["status"] = "failed"
        (output / "presentation-manifest.json").write_text(json.dumps(document))

    monkeypatch.setattr(executive_render, "_run_renderer", invalid)
    result = executive_render.render_executive(sealed(tmp_path), tmp_path / "output")
    assert result["artifacts"]["deck"]["status"] == "failed"
    assert not (tmp_path / "output/static-site.zip").exists()


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
    with pytest.raises(subprocess.TimeoutExpired):
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


@pytest.mark.parametrize("failure", [None, "speech", "record", "pdf", "content"])
@pytest.mark.parametrize("template", [3, 4])
def test_narration_stages_preserve_deck_and_reviewed_source(
    tmp_path, monkeypatch, failure, template
):
    from tests.executive_fixtures import make_v3_input

    from tests.test_executive_inputs import generic_documents, generic_seal

    run = tmp_path / "run"
    package = (
        generic_seal(run, generic_documents(run, 1))
        if template == 4
        else make_v3_input(run, slides=8)
    )
    verified = executive_render.verify_inputs(package)
    root = tmp_path / "renderer"
    root.mkdir()
    for name in (
        "render.mjs",
        "audio.mjs",
        "storyboard.mjs",
        "check-timing.mjs",
        "requirements.lock",
    ):
        (root / name).write_text("trusted runtime")
    monkeypatch.setenv("AUTOPOC_RENDERER_ROOT", str(root))
    monkeypatch.setenv("AUTOPOC_SPEECH_PYTHON", "/trusted/speech-python")
    monkeypatch.setenv("AUTOPOC_SPEECH_ASSETS", str(tmp_path / "assets"))
    calls = []

    def fake(command, **kwargs):
        assert 0 < kwargs["timeout"] <= 3000
        if command[0] == "node":
            stage = command[command.index("--stage") + 1]
            data, output = map(Path, command[2:4])
            calls.append(stage)
            if stage == "prepare":
                if template == 4:
                    from autopoc.executive_story import derive_checks

                    assert json.loads((data / "checks.json").read_text()) == derive_checks(
                        verified["evidence_index"]
                    )
                    assert json.loads((data / "visuals.json").read_text()) == verified["visuals"]
                    image = data / "visuals/assets/image0.png"
                    assert (
                        hashlib.sha256(image.read_bytes()).hexdigest()
                        == verified["visuals"]["assets"][0]["sha256"]
                    )
                source = output / "source"
                (source / "dist").mkdir(parents=True)
                (source / "dist/index.html").write_text("prepared deck")
                if template == 4:
                    for base in [source / "public/visuals", source / "dist/visuals"]:
                        base.mkdir(parents=True)
                        (base / "image0.png").write_bytes(image.read_bytes())
                (source / "slides.md").write_text("<ExecutiveSlide />")
                (source / "transcript.txt").write_text("Exact reviewed sentences")
                (output / "executive-summary.pdf").write_bytes(b"%PDF")
                (output / "presentation-manifest.json").write_text(
                    json.dumps(
                        {
                            "artifacts": {
                                "deck": {"status": "validated"},
                                "pdf": {"status": "validated"},
                            }
                        }
                    )
                )
                if failure in {"pdf", "content"}:
                    state = json.loads((output / "presentation-manifest.json").read_text())
                    state["artifacts"]["pdf"]["status"] = "failed"
                    if failure == "content":
                        state["artifacts"]["deck"]["status"] = "failed"
                    (output / "presentation-manifest.json").write_text(json.dumps(state))
                    raise subprocess.CalledProcessError(1, command)
            else:
                assert calls == ["prepare", "speech", "record"]
                assert "--timeline" in command
                if failure == "record":
                    raise subprocess.CalledProcessError(1, command)
                (output / "executive-summary.mp4").write_bytes(b"narrated video")
                manifest = json.loads((output / "presentation-manifest.json").read_text())
                manifest["artifacts"]["video"] = {"status": "validated"}
                manifest["scenes"] = [{"id": "slide-0", "duration_seconds": 31}]
                (output / "presentation-manifest.json").write_text(json.dumps(manifest))
        else:
            assert calls == ["prepare"]
            narrative = Path(command[command.index("--narrative") + 1])
            assert json.loads(narrative.read_text()) == verified["narrative"]
            calls.append("speech")
            assert command[:3] == ["/trusted/speech-python", "-m", "autopoc.executive_speech"]
            if failure == "speech":
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            speech = Path(command[command.index("--output-dir") + 1])
            speech.mkdir()
            (speech / "narration").mkdir()
            (speech / "narration/slide-0.wav").write_bytes(b"PCM")
            (speech / "timeline.json").write_text(
                json.dumps({"duration_seconds": 248, "scenes": []})
            )
            (speech / "transcript.txt").write_text("Exact reviewed sentences")
            (speech / "captions.vtt").write_text(
                "WEBVTT\n\n00:00:00.350 --> 00:00:01.350\nExact reviewed sentences\n"
            )

    monkeypatch.setattr(executive_render, "_run_renderer", fake)
    result = executive_render.render_executive(package, tmp_path / "output")
    assert calls == (
        ["prepare"]
        if failure == "content"
        else ["prepare", "speech"]
        if failure == "speech"
        else ["prepare", "speech", "record"]
    )
    assert result["status"] == ("partial" if failure else "generated_unpublished")
    assert set(result["artifacts"]) == {"source", "deck", "pdf", "video", "summary"}
    for kind in ("source", "summary"):
        assert result["artifacts"][kind]["status"] == "generated_unpublished"
    assert result["artifacts"]["deck"]["status"] == (
        "failed" if failure == "content" else "generated_unpublished"
    )
    assert result["artifacts"]["pdf"]["status"] == (
        "failed" if failure in {"pdf", "content"} else "generated_unpublished"
    )
    assert result["artifacts"]["video"]["status"] == (
        "failed" if failure in {"speech", "record", "content"} else "generated_unpublished"
    )
    summary = (tmp_path / "output/executive-summary.md").read_text()
    assert "Silent video" not in summary
    with zipfile.ZipFile(tmp_path / "output/executable-source.zip") as source:
        assert {
            "storyboard.mjs",
            "audio.mjs",
            "check-timing.mjs",
            "requirements.lock",
            "transcript.txt",
        } <= set(source.namelist())
        if template == 4:
            from autopoc.executive_story import derive_checks

            assert json.loads(source.read("checks.json")) == derive_checks(
                verified["evidence_index"]
            )
            assert json.loads(source.read("visuals.json")) == verified["visuals"]
            assert (
                hashlib.sha256(source.read("public/visuals/image0.png")).hexdigest()
                == verified["visuals"]["assets"][0]["sha256"]
            )
        if template == 4 and failure != "content":
            with zipfile.ZipFile(tmp_path / "output/static-site.zip") as site:
                assert json.loads(site.read("checks.json")) == derive_checks(
                    verified["evidence_index"]
                )
                assert json.loads(site.read("visuals.json")) == verified["visuals"]
                assert site.read("visuals/image0.png") == source.read("public/visuals/image0.png")
        if failure not in {"speech", "content"}:
            # Captions and the lexicon travel with recovery: a recovered render
            # must show the exact cues and pronunciations the timeline names.
            assert {
                "timeline.json",
                "narration/slide-0.wav",
                "captions.vtt",
                "speech-assets/kokoro_lexicon.json",
            } <= set(source.namelist())


def test_narrated_timeout_bound_is_distinct_from_legacy(tmp_path, monkeypatch):
    from tests.executive_fixtures import make_v3_input

    package = make_v3_input(tmp_path / "run")
    with pytest.raises(ValueError, match="timeout"):
        executive_render.render_executive(package, tmp_path / "output", timeout=3001)
    old = tmp_path / "legacy"
    old.mkdir()
    with pytest.raises(ValueError, match="timeout"):
        executive_render.render_executive(sealed(old), tmp_path / "old", timeout=601)


def test_local_cli_propagates_explicit_budget(monkeypatch, capsys):
    parser = argparse.ArgumentParser()
    executive_render.register_cli(parser.add_subparsers())
    args = parser.parse_args(
        [
            "executive-render",
            "--inputs",
            "sealed.zip",
            "--output-dir",
            "output",
            "--timeout-seconds",
            "2500",
        ]
    )
    calls = []

    def render(*args, **kwargs):
        calls.append(kwargs)
        return {"status": "generated_unpublished"}

    monkeypatch.setattr(executive_render, "render_executive", render)
    args.func(args)
    assert calls == [{"timeout": 2500}]


def test_schema3_changed_visual_payload_fails_before_any_render_process(tmp_path, monkeypatch):
    from tests.test_executive_inputs import generic_documents, generic_seal, rewrite_package

    package = generic_seal(tmp_path, generic_documents(tmp_path, 1))

    def alter(data):
        data["visuals.zip"] += b"changed reviewed asset bytes"

    altered = rewrite_package(package, tmp_path / "altered.zip", alter)
    calls = []
    monkeypatch.setattr(
        executive_render, "_run_renderer", lambda *args, **kwargs: calls.append(args)
    )
    with pytest.raises(ValueError, match="review"):
        executive_render.render_executive(altered, tmp_path / "output")
    assert calls == []
    assert not (tmp_path / "output").exists()


def test_schema3_recovery_source_keeps_assets_when_preparation_cannot_start(tmp_path, monkeypatch):
    from tests.test_executive_inputs import generic_documents, generic_seal

    package = generic_seal(tmp_path, generic_documents(tmp_path, 1))
    verified = executive_render.verify_inputs(package)

    def fail(*args, **kwargs):
        raise OSError("renderer unavailable")

    monkeypatch.setattr(executive_render, "_run_renderer", fail)
    result = executive_render.render_executive(package, tmp_path / "output")
    assert result["status"] == "partial"
    with zipfile.ZipFile(tmp_path / "output/executable-source.zip") as source:
        image = source.read("public/visuals/image0.png")
        assert hashlib.sha256(image).hexdigest() == verified["visuals"]["assets"][0]["sha256"]
        assert source.read("render-inputs.zip") == package.read_bytes()
