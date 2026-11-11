"""Offline renderer-only Heart inference and sample-derived narration timelines."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import math
import os
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from autopoc.evidence import _json
from autopoc.executive_story import MARKUP, validate_scene_plan

MODEL_REVISION = "f3ff3571791e39611d31c381e3a41a3af07b4987"
MODEL_FILES = {"config.json", "kokoro-v1_0.pth", "voices/af_heart.pt"}
SAMPLE_RATE = 24000
# Misaki's American inventory plus the pinned Kokoro model's measured T flap.
# The 10 November 2026 Heart audition verified model vocab and inline g2p retain
# T although Misaki's exported US_VOCAB omits it. Reject all other unknowns.
US_VOCAB = frozenset("AIOWYTbdfhijklmnpstuvwzæðŋɑɔəɛɜɡɪɹɾʃʊʌʒʤʧˈˌθᵊᵻʔ")
LEXICON_PATH = Path(__file__).with_name("kokoro_lexicon.json")


def _safe(path: Path) -> None:
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Speech files must be regular, non-symlink paths")


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_speech_assets(asset_root: Path) -> dict:
    """Validate image-owned assets without network access or optional imports."""
    _safe(asset_root)
    path = asset_root / "manifest.json"
    _safe(path)
    try:
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("Invalid speech manifest size")
        manifest = _json(path.read_bytes())
        if (
            manifest.get("schema_version") != 1
            or manifest.get("model") != "hexgrad/Kokoro-82M"
            or manifest.get("revision") != MODEL_REVISION
            or manifest.get("voice") != "af_heart"
            or manifest.get("language") != "en-US"
            or manifest.get("language_model")
            != {"distribution": "en-core-web-sm", "version": "3.8.0"}
            or set(manifest["files"]) != MODEL_FILES
            # _HeartEngine reads manifest["packages"] outside the except that
            # converts asset problems into this ValueError; require it here.
            or not isinstance(manifest.get("packages"), dict)
        ):
            raise ValueError("Unsupported offline speech assets")
        for name, metadata in manifest["files"].items():
            source = asset_root / name
            _safe(source)
            if (
                not source.is_file()
                or type(metadata["size"]) is not int
                or source.stat().st_size != metadata["size"]
                or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"])
                or _sha(source) != metadata["sha256"]
            ):
                raise ValueError("Missing or corrupt offline speech asset")
        return manifest
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Offline speech assets are unavailable") from exc


@dataclass(frozen=True)
class Lexicon:
    """Synthesis-only pronunciations; visible text and transcripts stay exact."""

    entries: dict[str, str]
    sha256: str | None
    pattern: re.Pattern | None

    def apply(self, text: str) -> str:
        if self.pattern is None:
            return text
        return self.pattern.sub(lambda m: f"[{m[0]}](/{self.entries[m[0]]}/)", text)


def load_lexicon(path: Path = LEXICON_PATH) -> Lexicon:
    """Reject unsupported symbols rather than let inference drop them silently."""
    _safe(path)
    try:
        if path.stat().st_size > 64 * 1024:
            raise ValueError("Invalid pronunciation lexicon size")
        document = _json(path.read_bytes())
        if document.get("schema_version") != 1 or document.get("language") != "en-US":
            raise ValueError("Unsupported pronunciation lexicon")
        entries = document["entries"]
        if not isinstance(entries, dict) or not 1 <= len(entries) <= 256:
            raise ValueError("Unsupported pronunciation lexicon")
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Pronunciation lexicon is unavailable") from exc
    for token, phonemes in entries.items():
        if (
            not isinstance(token, str)
            or not re.fullmatch(r"[A-Za-z][A-Za-z0-9+.-]{0,63}", token)
            or not isinstance(phonemes, str)
            or not 1 <= len(phonemes) <= 64
            or not set(phonemes) <= US_VOCAB
        ):
            raise ValueError(f"Unsupported pronunciation entry: {token!r}")
    # Longest first so a token never matches inside a longer entry.
    pattern = re.compile(
        r"(?<![\w-])(?:%s)(?![\w-])"
        % "|".join(re.escape(t) for t in sorted(entries, key=len, reverse=True))
    )
    return Lexicon(entries, _sha(path), pattern)


LEXICON = load_lexicon()
NO_LEXICON = Lexicon({}, None, None)


@dataclass(frozen=True)
class SpeechChunk:
    sample_rate: int
    pcm16: bytes


class SpeechEngine(Protocol):
    def synthesize(self, text: str) -> SpeechChunk: ...


class _HeartEngine:
    def __init__(self, root: Path, manifest: dict):
        # Set offline mode before importing any library that could access HF.
        os.environ.update(
            HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_IMPLICIT_TOKEN="1"
        )
        try:
            for name, version in manifest["packages"].items():
                if importlib.metadata.version(name) != version:
                    raise ValueError("Speech dependency version differs from asset manifest")
            language = manifest["language_model"]
            if importlib.metadata.version(language["distribution"]) != language["version"]:
                raise ValueError("English language asset version differs")
            self.np = importlib.import_module("numpy")
            torch = importlib.import_module("torch")
            spacy = importlib.import_module("spacy")
            if not spacy.util.is_package("en_core_web_sm"):
                raise ValueError("Packaged English language model is missing")
            spacy.load("en_core_web_sm", enable=["tok2vec", "tagger"])
            kokoro = importlib.import_module("kokoro")
            torch.set_num_threads(2)
            torch.set_num_interop_threads(1)
            model = (
                kokoro.KModel(
                    repo_id="hexgrad/Kokoro-82M",
                    config=str(root / "config.json"),
                    model=str(root / "kokoro-v1_0.pth"),
                )
                .to("cpu")
                .eval()
            )
            self.pipeline = kokoro.KPipeline(
                lang_code="a", repo_id="hexgrad/Kokoro-82M", model=model, device="cpu"
            )
            if self.pipeline.g2p.fallback is None:
                raise ValueError("Packaged English pronunciation fallback is missing")
            self.voice = str(root / "voices/af_heart.pt")
        except (ImportError, OSError, importlib.metadata.PackageNotFoundError) as exc:
            raise ValueError(
                "Renderer-only speech dependencies or English assets are unavailable"
            ) from exc

    def synthesize(self, text: str) -> SpeechChunk:
        chunks = [
            result.audio.detach().cpu().numpy()
            for result in self.pipeline(text, voice=self.voice, speed=0.95)
        ]
        if not chunks:
            raise ValueError("Speech engine produced no audio")
        audio = self.np.concatenate(chunks)
        if not self.np.isfinite(audio).all() or self.np.max(self.np.abs(audio)) > 1:
            raise ValueError("Speech engine produced an invalid waveform")
        return SpeechChunk(SAMPLE_RATE, self.np.rint(audio * 32767).astype("<i2").tobytes())


def _cue_time(seconds: float) -> str:
    whole, milliseconds = divmod(round(seconds * 1000), 1000)
    minutes, second = divmod(whole, 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}:{second:02d}.{milliseconds:03d}"


def _cue_text(text: str) -> str:
    """WebVTT reads &, < and > as markup; the spoken script stays exact."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _write_wav(path: Path, pcm: bytes) -> None:
    _safe(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
        audio.writeframes(pcm)


def generate_narration(
    narrative_path: Path,
    scenes_path: Path,
    output_dir: Path,
    *,
    asset_root: Path,
    engine: SpeechEngine | None = None,
) -> dict:
    """Write exact reviewed sentences and a measured timeline; never guess durations."""
    for path in (narrative_path, scenes_path, output_dir):
        _safe(path)
    manifest = verify_speech_assets(asset_root)
    narrative, plan = _json(narrative_path.read_bytes()), _json(scenes_path.read_bytes())
    validate_scene_plan(plan, narrative)
    identity = _sha(asset_root / "manifest.json")
    if plan["narration"]["model_manifest_sha256"] != identity:
        raise ValueError("Reviewed speech model identity differs from packaged assets")
    # Absent identity means the scene plan was reviewed without overrides; keep
    # those renders byte-comparable instead of silently changing pronunciation.
    reviewed = plan["narration"].get("lexicon_sha256")
    lexicon = NO_LEXICON if reviewed is None else LEXICON
    if reviewed is not None and reviewed != LEXICON.sha256:
        raise ValueError("Reviewed pronunciation lexicon differs from the packaged lexicon")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError("Narration output must be a new directory")
    if engine is None:
        engine = _HeartEngine(asset_root, manifest)
    output_dir.mkdir(parents=True, mode=0o700, exist_ok=True)
    policy, entries, transcript, total_frames = plan["timing_policy"], [], [], 0
    cues = ["WEBVTT", ""]
    for slide in narrative["slides"]:
        identity = slide["id"]
        if not isinstance(identity, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", identity
        ):
            raise ValueError("Invalid narration scene identifier")
        sentences = slide.get("narration")
        if not isinstance(sentences, list) or not 1 <= len(sentences) <= 12:
            raise ValueError("Missing reviewed narration sentences")
        if sum(len(s["text"].split()) for s in sentences) > 180:
            raise ValueError("Narration exceeds reviewed word limit")
        pieces, offsets, sentence_files, sample_count = [], [], [], 0
        for i, sentence in enumerate(sentences):
            text = sentence["text"]
            if not isinstance(text, str) or not text.strip() or len(text) > 2000:
                raise ValueError("Invalid reviewed narration sentence")
            if MARKUP.search(text):
                raise ValueError("Reviewed narration must not contain engine markup")
            chunk = engine.synthesize(lexicon.apply(text))
            if (
                type(chunk.sample_rate) is not int
                or chunk.sample_rate != SAMPLE_RATE
                or not isinstance(chunk.pcm16, bytes)
                or not chunk.pcm16
                or len(chunk.pcm16) % 2
                or not any(chunk.pcm16)
            ):
                raise ValueError("Speech engine produced invalid PCM audio")
            if i:
                gap = int(policy["sentence_gap_seconds"] * SAMPLE_RATE)
                pieces.append(b"\0\0" * gap)
                sample_count += gap
            start = sample_count / SAMPLE_RATE
            sample_count += len(chunk.pcm16) // 2
            if (
                sample_count / SAMPLE_RATE + policy["lead_seconds"] + policy["tail_seconds"]
                > policy["max_scene_seconds"]
            ):
                raise ValueError("Measured scene duration exceeds policy; revise content")
            offsets.append({"start_seconds": start, "end_seconds": sample_count / SAMPLE_RATE})
            path = output_dir / "narration" / identity / f"sentence-{i + 1}.wav"
            _write_wav(path, chunk.pcm16)
            sentence_files.append(
                {"path": path.relative_to(output_dir).as_posix(), "sha256": _sha(path)}
            )
            pieces.append(chunk.pcm16)
        audio_seconds = sample_count / SAMPLE_RATE
        duration = max(
            policy["min_scene_seconds"],
            audio_seconds + policy["lead_seconds"] + policy["tail_seconds"],
        )
        frames = math.ceil(duration * 30)
        if (
            frames / 30 > policy["max_scene_seconds"]
            or (total_frames + frames) / 30 > policy["max_total_seconds"]
        ):
            raise ValueError("Measured narration duration exceeds policy; revise content")
        path = output_dir / "narration" / f"{identity}.wav"
        _write_wav(path, b"".join(pieces))
        entries.append(
            {
                "id": identity,
                "audio_path": path.relative_to(output_dir).as_posix(),
                "audio_sha256": _sha(path),
                "audio_seconds": audio_seconds,
                "duration_seconds": frames / 30,
                "frame_count": frames,
                "start_seconds": total_frames / 30,
                "sentence_offsets": offsets,
                "sentence_audio": sentence_files,
            }
        )
        speech_start = total_frames / 30 + policy["lead_seconds"]
        for offset, sentence in zip(offsets, sentences):
            cues.append(
                f"{_cue_time(speech_start + offset['start_seconds'])} -->"
                f" {_cue_time(speech_start + offset['end_seconds'])}"
            )
            cues.extend([_cue_text(sentence["text"]), ""])
        total_frames += frames
        transcript.extend([slide["title"], *(s["text"] for s in sentences), ""])
    captions = output_dir / "captions.vtt"
    captions.write_text("\n".join(cues), encoding="utf-8")
    timeline = {
        "schema_version": 1,
        "run_id": narrative["run_id"],
        "narrative_sha256": _sha(narrative_path),
        "scenes_sha256": _sha(scenes_path),
        "narration": plan["narration"],
        "model_revision": manifest["revision"],
        "lexicon_sha256": lexicon.sha256,
        "captions_path": captions.name,
        "captions_sha256": _sha(captions),
        "sample_rate": SAMPLE_RATE,
        "fps": 30,
        "duration_seconds": total_frames / 30,
        "scenes": entries,
    }
    (output_dir / "transcript.txt").write_text("\n".join(transcript), encoding="utf-8")
    (output_dir / "timeline.json").write_text(json.dumps(timeline, indent=2) + "\n")
    return timeline


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("narrative", "scenes", "output-dir", "asset-root"):
        parser.add_argument("--" + option, type=Path, required=True)
    args = parser.parse_args()
    result = generate_narration(
        args.narrative, args.scenes, args.output_dir, asset_root=args.asset_root
    )
    print(json.dumps({"status": "generated_local", "duration_seconds": result["duration_seconds"]}))


if __name__ == "__main__":
    main()
