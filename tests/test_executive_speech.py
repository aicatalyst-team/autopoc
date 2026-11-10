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


def inputs(tmp_path, *, slides=6, lexicon=False, generic=False):
    from autopoc.executive_speech import LEXICON
    from tests.test_executive_inputs import generic_documents

    assets = speech_assets(tmp_path / "assets")
    docs = (
        generic_documents(tmp_path / "run", 1)
        if generic
        else v3_documents(tmp_path / "run", slides=slides)
    )
    scenes = json.loads(docs[2].read_text())
    scenes["narration"]["model_manifest_sha256"] = hashlib.sha256(
        (assets / "manifest.json").read_bytes()
    ).hexdigest()
    if lexicon:
        scenes["narration"]["lexicon_sha256"] = LEXICON.sha256
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


class RecordingEngine(PCMEngine):
    def __init__(self, **options):
        super().__init__(**options)
        self.texts = []

    def synthesize(self, text):
        self.texts.append(text)
        return super().synthesize(text)


def with_narration(narrative, text):
    doc = json.loads(narrative.read_text())
    doc["slides"][0]["narration"] = [{"text": text, "claim_ids": ["claim-0"]}]
    narrative.write_text(json.dumps(doc))
    return doc


def test_lexicon_guides_synthesis_without_altering_reviewed_text(tmp_path):
    """Pronunciation is a synthesis detail; reviewed and published text is exact."""
    from autopoc.executive_speech import LEXICON, generate_narration

    narrative, scenes, assets = inputs(tmp_path, lexicon=True)
    with_narration(narrative, "We completed the PoC.")
    engine = RecordingEngine()
    result = generate_narration(
        narrative, scenes, tmp_path / "output", asset_root=assets, engine=engine
    )
    assert engine.texts[0] == f"We completed the [PoC](/{LEXICON.entries['PoC']}/)."
    assert "We completed the PoC." in (tmp_path / "output" / "transcript.txt").read_text()
    assert result["lexicon_sha256"] == LEXICON.sha256


def test_changed_pronunciation_cannot_reuse_a_reviewed_speech_identity(tmp_path):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path, lexicon=True)
    plan = json.loads(scenes.read_text())
    plan["narration"]["lexicon_sha256"] = "0" * 64
    scenes.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="lexicon"):
        generate_narration(
            narrative, scenes, tmp_path / "output", asset_root=assets, engine=PCMEngine()
        )


def test_inputs_sealed_before_the_lexicon_keep_their_original_pronunciation(tmp_path):
    """Absent identity means no overrides, so recovered renders stay comparable."""
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path)
    with_narration(narrative, "We completed the PoC.")
    engine = RecordingEngine()
    result = generate_narration(
        narrative, scenes, tmp_path / "output", asset_root=assets, engine=engine
    )
    assert engine.texts[0] == "We completed the PoC."
    assert result["lexicon_sha256"] is None


def test_reviewed_text_cannot_smuggle_engine_phoneme_markup(tmp_path):
    """Misaki reads [word](/ips/) as an override, so scripts must not contain it."""
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path, lexicon=True)
    with_narration(narrative, "The deployment [failed](/sʌksˈɛst/) on the first attempt.")
    with pytest.raises(ValueError, match="markup"):
        generate_narration(
            narrative, scenes, tmp_path / "output", asset_root=assets, engine=PCMEngine()
        )


def test_every_entry_records_the_default_it_replaces(tmp_path):
    """Overrides are only justified by a measured-wrong default.

    Comparing Misaki's g2p with and without each override inside the renderer
    image on 9 November 2026 showed its defaults are mostly right: NVIDIA, Quay,
    UBI, UBI9 and mTLS were already correct, and an override for UBI9 was worse
    than the default because it dropped the word break before "nine". An entry
    with no recorded default is an assumption, so require the evidence.
    """
    from autopoc.executive_speech import LEXICON, LEXICON_PATH

    document = json.loads(LEXICON_PATH.read_text())
    assert set(document["measured_defaults"]) == set(LEXICON.entries)
    for token, default in document["measured_defaults"].items():
        assert default != LEXICON.entries[token], f"{token} override matches the default"
    for already_correct in ("NVIDIA", "Quay", "UBI", "UBI9", "mTLS"):
        assert already_correct not in LEXICON.entries, already_correct


def test_overrides_never_fire_inside_a_longer_token(tmp_path):
    """A partial match would mispronounce the whole word, so every spoken
    surface form needs its own entry rather than relying on a prefix.
    """
    from autopoc.executive_speech import Lexicon, load_lexicon

    path = tmp_path / "lex.json"
    path.write_text(
        json.dumps({"schema_version": 1, "language": "en-US", "entries": {"UBI": "jˌubˌiˈI"}})
    )
    lexicon = load_lexicon(path)
    assert isinstance(lexicon, Lexicon)
    assert lexicon.apply("Built on UBI9 images.") == "Built on UBI9 images."
    assert lexicon.apply("They are UBIquitous.") == "They are UBIquitous."
    assert lexicon.apply("Built on UBI images.") == "Built on [UBI](/jˌubˌiˈI/) images."


def test_packaged_lexicon_only_uses_supported_american_phonemes(tmp_path):
    """Symbols outside Misaki's US vocabulary are dropped silently at inference."""
    from autopoc.executive_speech import US_VOCAB, LEXICON, load_lexicon

    assert LEXICON.entries
    for token, phonemes in LEXICON.entries.items():
        assert set(phonemes) <= US_VOCAB, (token, set(phonemes) - US_VOCAB)
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps({"schema_version": 1, "entries": {"PoC": "kgi"}}))
    with pytest.raises(ValueError):
        load_lexicon(broken)


@pytest.mark.parametrize("generic", [False, True])
def test_measured_sentence_samples_preserve_offsets_and_script(tmp_path, generic):
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path, generic=generic)
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


@pytest.mark.parametrize("generic", [False, True])
def test_captions_follow_measured_speech_and_quote_the_reviewed_script(tmp_path, generic):
    """Cue times are scene start plus the lead-in plus the measured offsets."""
    from autopoc.executive_speech import generate_narration

    narrative, scenes, assets = inputs(tmp_path, generic=generic)
    doc = json.loads(narrative.read_text())
    doc["slides"][0]["narration"] = [
        {"text": "Results & caveats for <one> server.", "claim_ids": ["claim-0"]},
        {"text": "A second reviewed sentence.", "claim_ids": ["claim-0"]},
    ]
    narrative.write_text(json.dumps(doc))
    result = generate_narration(
        narrative, scenes, tmp_path / "output", asset_root=assets, engine=PCMEngine()
    )
    captions = (tmp_path / "output" / "captions.vtt").read_text(encoding="utf-8")
    assert captions.startswith("WEBVTT\n\n")
    assert (
        "00:00:00.350 --> 00:00:01.350\nResults &amp; caveats for &lt;one&gt; server." in captions
    )
    assert "00:00:01.550 --> 00:00:02.550\nA second reviewed sentence." in captions
    assert "00:00:06.350 --> 00:00:07.350" in captions
    assert result["captions_sha256"] == hashlib.sha256(captions.encode()).hexdigest()
    assert captions.count("-->") == sum(len(s["sentence_offsets"]) for s in result["scenes"])


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
