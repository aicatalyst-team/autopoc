"""Actual PCM samples determine narration timing; optional inference stays offline."""

import hashlib
import json
import struct
import wave

import pytest

from tests.executive_fixtures import v3_documents


def speech_assets(root):
    root.mkdir()
    files = {}
    for name, data in {
        "config.json": b"{}",
        "kokoro-v1_0.pth": b"model",
        "voices/af_heart.pt": b"voice",
    }.items():
        path = root / name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(data)
        files[name] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    manifest = {
        "schema_version": 1,
        "model": "hexgrad/Kokoro-82M",
        "revision": "f3ff3571791e39611d31c381e3a41a3af07b4987",
        "voice": "af_heart",
        "language": "en-US",
        "language_model": {"distribution": "en-core-web-sm", "version": "3.8.0"},
        "files": files,
        "packages": {"kokoro": "0.9.4", "misaki": "0.9.4", "torch": "2.8.0+cpu"},
    }
    (root / "manifest.json").write_text(json.dumps(manifest))
    return root


def inputs(tmp_path, *, slides=6):
    assets = speech_assets(tmp_path / "assets")
    docs = v3_documents(tmp_path / "run", slides=slides)
    scenes = json.loads(docs[2].read_text())
    scenes["narration"]["model_manifest_sha256"] = hashlib.sha256(
        (assets / "manifest.json").read_bytes()
    ).hexdigest()
    docs[2].write_text(json.dumps(scenes))
    return docs[1], docs[2], assets


class PCMEngine:
    def __init__(self, *, seconds=1, sample_rate=24000, pcm=None):
        self.seconds, self.sample_rate, self.pcm = seconds, sample_rate, pcm

    def synthesize(self, text):
        from autopoc.executive_speech import SpeechChunk

        pcm = (
            self.pcm
            if self.pcm is not None
            else struct.pack("<h", 1000) * int(24000 * self.seconds)
        )
        return SpeechChunk(self.sample_rate, pcm)


def test_measured_sentence_samples_preserve_offsets_and_script(tmp_path):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path)
    doc = json.loads(narrative.read_text())
    doc["slides"][0]["narration"].append(
        {"text": "A second reviewed sentence.", "claim_ids": ["claim-0"]}
    )
    narrative.write_text(json.dumps(doc))
    result = generate_narration(
        narrative, scenes, tmp_path / "output", asset_root=assets, engine=PCMEngine()
    )
    first = result["scenes"][0]
    assert first["audio_seconds"] == 2.2
    assert first["duration_seconds"] == 6.0
    assert first["sentence_offsets"] == [
        {"start_seconds": 0.0, "end_seconds": 1.0},
        {"start_seconds": 1.2, "end_seconds": 2.2},
    ]
    assert result["scenes"][1]["start_seconds"] == 6.0
    assert result["duration_seconds"] == 36.0
    with wave.open(str(tmp_path / "output" / first["audio_path"]), "rb") as audio:
        assert (
            audio.getframerate(),
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getnframes(),
        ) == (24000, 1, 2, 52800)
    assert "A second reviewed sentence." in (tmp_path / "output" / "transcript.txt").read_text()
    assert json.loads((tmp_path / "output" / "timeline.json").read_text()) == result


def test_long_audio_extends_scene_instead_of_speeding_or_clipping(tmp_path):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path)
    result = generate_narration(
        narrative, scenes, tmp_path / "output", asset_root=assets, engine=PCMEngine(seconds=10)
    )
    assert result["scenes"][0]["audio_seconds"] == 10.0
    assert result["scenes"][0]["duration_seconds"] == 11.0
    assert result["duration_seconds"] == 66.0


@pytest.mark.parametrize(
    "sample_rate,pcm",
    [
        (22050, b"xx"),
        (float("nan"), b"xx"),
        (24000, b""),
        (24000, b"x"),
        (24000, b"\x00\x00"),
        (24000, "invalid"),
    ],
)
def test_invalid_engine_audio_never_becomes_a_successful_scene(tmp_path, sample_rate, pcm):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path)
    with pytest.raises(ValueError):
        generate_narration(
            narrative,
            scenes,
            tmp_path / "output",
            asset_root=assets,
            engine=PCMEngine(sample_rate=sample_rate, pcm=pcm),
        )
    assert not (tmp_path / "output" / "timeline.json").exists()


@pytest.mark.parametrize("change", ["missing", "changed", "symlink", "language", "manifest_hash"])
def test_missing_or_changed_packaged_assets_fail_before_inference(tmp_path, change):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path)
    voice = assets / "voices/af_heart.pt"
    if change == "missing":
        voice.unlink()
    elif change == "changed":
        voice.write_bytes(b"changed")
    elif change == "symlink":
        source = tmp_path / "voice.pt"
        source.write_bytes(voice.read_bytes())
        voice.unlink()
        voice.symlink_to(source)
    else:
        manifest = json.loads((assets / "manifest.json").read_text())
        if change == "language":
            del manifest["language_model"]
        else:
            manifest["revision"] = "0" * 40
        (assets / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        generate_narration(
            narrative, scenes, tmp_path / "output", asset_root=assets, engine=PCMEngine()
        )


@pytest.mark.parametrize("seconds,slides", [(120, 6), (100, 10)])
def test_operational_duration_limits_reject_instead_of_truncating(tmp_path, seconds, slides):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path, slides=slides)
    with pytest.raises(ValueError, match="duration"):
        generate_narration(
            narrative,
            scenes,
            tmp_path / "output",
            asset_root=assets,
            engine=PCMEngine(seconds=seconds),
        )
    assert not (tmp_path / "output" / "timeline.json").exists()


def test_output_reuse_cannot_overwrite_previous_audio(tmp_path):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    (output / "keep.txt").write_text("existing")
    with pytest.raises(ValueError):
        generate_narration(narrative, scenes, output, asset_root=assets, engine=PCMEngine())
    assert (output / "keep.txt").read_text() == "existing"


@pytest.mark.parametrize("corrupt", [False, True])
def test_build_preparer_verifies_cached_bytes_before_exposing_assets(tmp_path, corrupt):
    import subprocess
    import sys
    from pathlib import Path

    assets = speech_assets(tmp_path / "cache")
    if corrupt:
        (assets / "voices/af_heart.pt").write_bytes(b"corrupt")
    output = tmp_path / "packaged"
    script = Path(__file__).parents[1] / "scripts/prepare-kokoro-assets.py"
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--manifest",
            str(assets / "manifest.json"),
            "--cache-dir",
            str(assets),
            "--output-dir",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    if corrupt:
        assert result.returncode != 0
        assert not (output / "manifest.json").exists()
    else:
        assert result.returncode == 0, result.stderr
        from autopoc.executive_speech import verify_speech_assets

        assert verify_speech_assets(output)["voice"] == "af_heart"
        assert not (output / "voices/af_heart.pt").is_symlink()
