"""Bounded, deterministic, locally staged PNG assets for offline executive stories."""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import struct
import zipfile
import zlib
from datetime import datetime
from pathlib import Path

from autopoc.evidence import sanitize_text
from autopoc.executive_inputs import _dump, _json
from autopoc.executive_story import _https_reference

MAX_PNG = 2 * 1024 * 1024
MAX_EXPANDED = 8 * 1024 * 1024
MAX_ARCHIVE = MAX_EXPANDED + 65536
MAX_MANIFEST = 65536


def _need(value, message="Invalid executive visuals"):
    if not value:
        raise ValueError(message)


def _text(value, maximum=500):
    _need(isinstance(value, str) and 0 < len(value) <= maximum)
    _need(sanitize_text(value) == value and not any(ord(c) < 32 for c in value))


def _read(path: Path, limit: int) -> bytes:
    # Reject symlinks in parent components as well as the final file.
    _need(not any(p.is_symlink() for p in (path, *path.parents)))
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW), "rb") as stream:
        _need(stat.S_ISREG(os.fstat(stream.fileno()).st_mode))
        raw = stream.read(limit + 1)
    _need(len(raw) <= limit, "Visual input exceeds size limit")
    return raw


def _png(raw: bytes) -> tuple[int, int]:
    _need(len(raw) <= MAX_PNG and raw[:8] == b"\x89PNG\r\n\x1a\n", "Invalid PNG")
    offset, seen, idat_ended = 8, [], False
    width = height = color = depth = palette_size = 0
    allowed = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"sRGB", b"gAMA", b"cHRM"}
    while offset < len(raw):
        _need(offset + 12 <= len(raw), "Truncated PNG")
        length, kind = struct.unpack(">I4s", raw[offset : offset + 8])
        end = offset + 12 + length
        _need(end <= len(raw) and kind in allowed, "Invalid PNG chunk")
        payload = raw[offset + 8 : end - 4]
        _need(
            zlib.crc32(kind + payload) == struct.unpack(">I", raw[end - 4 : end])[0],
            "PNG CRC mismatch",
        )
        _need(kind == b"IHDR" if not seen else kind != b"IHDR", "Invalid PNG header order")
        if kind != b"IDAT" and b"IDAT" in seen:
            idat_ended = True
        if kind == b"IHDR":
            _need(length == 13)
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            _need(1 <= width <= 4096 and 1 <= height <= 4096 and depth in depths.get(color, ()))
            _need(compression == filtering == 0 and interlace in (0, 1))
        elif kind == b"IDAT":
            _need(not idat_ended and (color != 3 or b"PLTE" in seen))
        elif kind == b"IEND":
            _need(length == 0 and b"IDAT" in seen and end == len(raw))
        else:
            _need(kind not in seen and b"IDAT" not in seen)
            if kind == b"PLTE":
                _need(color not in (0, 4) and 0 < length <= 768 and length % 3 == 0)
                _need(b"tRNS" not in seen and (color != 3 or length // 3 <= 2**depth))
            elif kind == b"tRNS":
                _need(
                    (color == 0 and length == 2)
                    or (color == 2 and length == 6)
                    or (color == 3 and b"PLTE" in seen and 0 < length <= palette_size)
                )
            else:
                _need(b"PLTE" not in seen)
                _need(
                    (kind == b"sRGB" and length == 1 and payload[0] <= 3)
                    or (kind == b"gAMA" and length == 4 and int.from_bytes(payload, "big") > 0)
                    or (kind == b"cHRM" and length == 32)
                )
        if kind == b"PLTE":
            palette_size = length // 3
        seen.append(kind)
        offset = end
    _need(seen and seen[-1] == b"IEND", "Missing PNG end")
    # Full image decoding is deliberately performed by the offline browser before speech.
    return width, height


def _manifest(doc: dict, *, run_id: str, claim_ids: set[str]) -> dict:
    _need(isinstance(doc, dict) and set(doc) == {"schema_version", "run_id", "gaps", "assets"})
    _need(type(doc["schema_version"]) is int and doc["schema_version"] == 1)
    _need(
        isinstance(doc["run_id"], str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", doc["run_id"])
        and doc["run_id"] == run_id
    )
    _need(isinstance(doc["gaps"], list) and len(doc["gaps"]) <= 20)
    for gap in doc["gaps"]:
        _text(gap)
    _need(isinstance(doc["assets"], list) and len(doc["assets"]) <= 4)
    ids, pixels = set(), 0
    fields = {
        "id",
        "kind",
        "source_url",
        "source_revision",
        "claim_ids",
        "caption",
        "alt",
        "sha256",
        "width",
        "height",
        "attribution",
    }
    for asset in doc["assets"]:
        _need(isinstance(asset, dict) and fields <= set(asset) <= fields | {"captured_at"})
        ident = asset["id"]
        _need(
            isinstance(ident, str)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", ident)
            and ident not in ids
        )
        ids.add(ident)
        _need(asset["kind"] in ("source_capture", "project_brand", "concept"))
        if asset["source_url"] is None:
            _need(asset["kind"] == "concept")
        else:
            _https_reference(asset["source_url"])
        if asset["source_revision"] is not None:
            _text(asset["source_revision"], 200)
        for name in ("caption", "alt", "attribution"):
            _text(asset[name])
        _need(isinstance(asset["claim_ids"], list) and 1 <= len(asset["claim_ids"]) <= 512)
        _need(all(isinstance(c, str) and c in claim_ids for c in asset["claim_ids"]))
        _need(len(set(asset["claim_ids"])) == len(asset["claim_ids"]))
        _need(isinstance(asset["sha256"], str) and re.fullmatch("[0-9a-f]{64}", asset["sha256"]))
        for name in ("width", "height"):
            _need(type(asset[name]) is int and 1 <= asset[name] <= 4096)
        pixels += asset["width"] * asset["height"]
        if "captured_at" in asset:
            _need(
                isinstance(asset["captured_at"], str)
                and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", asset["captured_at"])
            )
            datetime.strptime(asset["captured_at"], "%Y-%m-%dT%H:%M:%SZ")
    _need(pixels <= 16_000_000, "Visual pixel budget exceeded")
    _need(sanitize_text(_dump(doc).decode()) == _dump(doc).decode())
    return doc


def _validate_assets(doc, data):
    for asset in doc["assets"]:
        raw = data[f"assets/{asset['id']}.png"]
        _need(hashlib.sha256(raw).hexdigest() == asset["sha256"], "Visual hash mismatch")
        _need(_png(raw) == (asset["width"], asset["height"]), "Visual dimensions mismatch")


def prepare_visuals(manifest_path: Path, output_path: Path) -> Path:
    """Package explicit adjacent assets/<id>.png files without fetching or editing bytes."""
    try:
        raw = _read(manifest_path, MAX_MANIFEST)
        doc = _json(raw)
        claims = {c for a in doc["assets"] for c in a["claim_ids"]}
        _manifest(doc, run_id=doc["run_id"], claim_ids=claims)
        data = {"manifest.json": _dump(doc)}
        for asset in doc["assets"]:
            data[f"assets/{asset['id']}.png"] = _read(
                manifest_path.parent / "assets" / f"{asset['id']}.png", MAX_PNG
            )
        _need(sum(map(len, data.values())) <= MAX_EXPANDED)
        _validate_assets(doc, data)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(data.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100600 << 16
                archive.writestr(info, content)
        _need(not output_path.is_symlink() and len(buffer.getvalue()) <= MAX_ARCHIVE)
        output_path.write_bytes(buffer.getvalue())
        return output_path
    except (OSError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Cannot prepare visuals") from exc


def verify_visuals(path: Path, *, run_id: str, claim_ids: set[str]) -> dict:
    """Verify exact archive membership, provenance and reviewed PNG bytes without extraction."""
    try:
        raw = _read(path, MAX_ARCHIVE)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            _need(1 <= len(entries) <= 5 and len({i.filename for i in entries}) == len(entries))
            _need(sum(i.file_size for i in entries) <= MAX_EXPANDED)
            _need(
                all(
                    not i.is_dir()
                    and not i.flag_bits & 1
                    and stat.S_IFMT(i.external_attr >> 16) != stat.S_IFLNK
                    and i.file_size <= (MAX_MANIFEST if i.filename == "manifest.json" else MAX_PNG)
                    for i in entries
                )
            )
            doc = _manifest(
                _json(archive.read("manifest.json")), run_id=run_id, claim_ids=claim_ids
            )
            _need(
                {i.filename for i in entries}
                == {"manifest.json"} | {f"assets/{a['id']}.png" for a in doc["assets"]}
            )
            data = {i.filename: archive.read(i) for i in entries}
        _validate_assets(doc, data)
        return doc
    except (
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        zipfile.BadZipFile,
        RuntimeError,
        struct.error,
    ) as exc:
        raise ValueError("Cannot verify visuals") from exc
