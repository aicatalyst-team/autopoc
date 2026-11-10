"""Reviewed visuals remain bounded, authentic local bytes through offline recovery."""

import hashlib
import json
import struct
import zipfile
import zlib

import pytest


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(width=1, height=1, extra=b""):
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + extra
        + chunk(b"IDAT", zlib.compress(b"\0\xff\0\0"))
        + chunk(b"IEND", b"")
    )


def staged(root, count=1):
    (root / "assets").mkdir(exist_ok=True)
    assets = []
    for i in range(count):
        raw = png()
        (root / f"assets/image{i}.png").write_bytes(raw)
        assets.append(
            {
                "id": f"image{i}",
                "kind": "source_capture",
                "source_url": "https://docs.example.org/",
                "source_revision": None,
                "claim_ids": ["c1"],
                "caption": "Contextual current documentation",
                "alt": "Documentation page",
                "sha256": hashlib.sha256(raw).hexdigest(),
                "width": 1,
                "height": 1,
                "attribution": "Example documentation",
                "captured_at": "2026-11-10T00:00:00Z",
            }
        )
    manifest = root / "manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "run_id": "run-1", "gaps": [], "assets": assets})
    )
    return manifest


def prepare(manifest, target):
    from autopoc.executive_visuals import prepare_visuals

    return prepare_visuals(manifest, target)


def verify(path, **kwargs):
    from autopoc.executive_visuals import verify_visuals

    return verify_visuals(
        path, run_id=kwargs.get("run_id", "run-1"), claim_ids=kwargs.get("claim_ids", {"c1"})
    )


@pytest.mark.parametrize("count", [0, 4])
def test_zero_or_four_visuals_have_deterministic_offline_bytes(tmp_path, count):
    source = staged(tmp_path, count)
    one = prepare(source, tmp_path / "one.zip")
    two = prepare(source, tmp_path / "two.zip")
    assert one.read_bytes() == two.read_bytes()
    assert len(verify(one)["assets"]) == count
    with zipfile.ZipFile(one) as archive:
        assert set(archive.namelist()) == {"manifest.json"} | {
            f"assets/image{i}.png" for i in range(count)
        }


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "geometry",
        "claim",
        "run",
        "fifth",
        "unknown",
        "secret",
        "url",
        "traversal",
        "kind",
        "path",
    ],
)
def test_invalid_reviewed_provenance_is_rejected(tmp_path, change):
    source = staged(tmp_path, 5 if change == "fifth" else 1)
    doc = json.loads(source.read_text())
    asset = doc["assets"][0]
    if change == "hash":
        asset["sha256"] = "0" * 64
    elif change == "geometry":
        asset["width"] = 2
    elif change == "claim":
        asset["claim_ids"] = ["missing"]
    elif change == "run":
        doc["run_id"] = "other"
    elif change == "unknown":
        doc["private"] = "hidden"
    elif change == "secret":
        asset["alt"] = "Bearer this-is-a-secret-token"
    elif change == "url":
        asset["source_url"] = "https://user:pass@example.org/"
    elif change == "traversal":
        asset["id"] = "../private"
    elif change == "kind":
        asset["kind"] = "runtime_screenshot"
    elif change == "path":
        asset["path"] = "/etc/passwd"
    source.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        verify(prepare(source, tmp_path / "out.zip"))


@pytest.mark.parametrize(
    "raw",
    [
        b"<svg/>",
        png(extra=chunk(b"tEXt", b"private")),
        png(extra=chunk(b"eXIf", b"private")),
        png(4097),
        png()[:-1],
        png() + b"extra",
        png().replace(b"IDAT", b"IDAX"),
    ],
)
def test_invalid_or_hidden_png_content_is_rejected(tmp_path, raw):
    source = staged(tmp_path)
    (tmp_path / "assets/image0.png").write_bytes(raw)
    doc = json.loads(source.read_text())
    doc["assets"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
    source.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        prepare(source, tmp_path / "out.zip")


@pytest.mark.parametrize("member", ["../escape", "other.txt", "assets/other.png", "manifest.json"])
def test_archive_member_injection_and_duplicates_are_rejected(tmp_path, member):
    path = prepare(staged(tmp_path), tmp_path / "out.zip")
    with zipfile.ZipFile(path, "a") as archive, __import__("warnings").catch_warnings():
        __import__("warnings").simplefilter("ignore")
        archive.writestr(member, b"{}")
    with pytest.raises(ValueError):
        verify(path)


def test_symlink_and_duplicate_manifest_keys_are_rejected(tmp_path):
    source = staged(tmp_path)
    asset = tmp_path / "assets/image0.png"
    raw = asset.read_bytes()
    asset.unlink()
    (tmp_path / "real.png").write_bytes(raw)
    asset.symlink_to(tmp_path / "real.png")
    with pytest.raises(ValueError):
        prepare(source, tmp_path / "out.zip")
    source.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError):
        prepare(source, tmp_path / "out.zip")


@pytest.mark.parametrize(
    "budget", ["png", "compressed", "expanded", "pixels", "symlink", "crc", "order"]
)
def test_resource_and_png_structure_guards(tmp_path, budget):
    source = staged(tmp_path, 4 if budget == "pixels" else 1)
    if budget == "png":
        (tmp_path / "assets/image0.png").write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    elif budget == "pixels":
        doc = json.loads(source.read_text())
        for asset in doc["assets"]:
            asset.update(width=4096, height=4096)
        source.write_text(json.dumps(doc))
    elif budget in ("crc", "order"):
        raw = png()
        if budget == "crc":
            raw = raw[:29] + b"xxxx" + raw[33:]
        else:
            raw = raw[:33] + chunk(b"IEND", b"") + raw[33:]
        (tmp_path / "assets/image0.png").write_bytes(raw)
        doc = json.loads(source.read_text())
        doc["assets"][0]["sha256"] = hashlib.sha256(raw).hexdigest()
        source.write_text(json.dumps(doc))
    else:
        target = tmp_path / "out.zip"
        if budget == "compressed":
            target.write_bytes(b"x" * (8 * 1024 * 1024 + 65537))
        else:
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                if budget == "expanded":
                    archive.writestr("manifest.json", b"x" * (8 * 1024 * 1024 + 1))
                else:
                    info = zipfile.ZipInfo("manifest.json")
                    info.external_attr = 0o120777 << 16
                    archive.writestr(info, b"{}")
        with pytest.raises(ValueError):
            verify(target)
        return
    with pytest.raises(ValueError):
        prepare(source, tmp_path / "out.zip")


def test_visual_identifiers_match_story_and_evidence_contract(tmp_path):
    source = staged(tmp_path)
    doc = json.loads(source.read_text())
    ident = "7" + "a" * 127
    doc["run_id"] = ident
    doc["assets"][0]["id"] = ident
    (tmp_path / "assets/image0.png").rename(tmp_path / f"assets/{ident}.png")
    source.write_text(json.dumps(doc))
    assert verify(prepare(source, tmp_path / "out.zip"), run_id=ident)["assets"][0]["id"] == ident


def test_nonregular_local_manifest_is_rejected_without_blocking(tmp_path):
    import os
    import subprocess
    import sys

    fifo = tmp_path / "manifest.json"
    os.mkfifo(fifo)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; from autopoc.executive_visuals import prepare_visuals; "
            "import sys; prepare_visuals(Path(sys.argv[1]), Path(sys.argv[2]))",
            str(fifo),
            str(tmp_path / "out.zip"),
        ],
        capture_output=True,
        timeout=2,
        check=False,
    )
    assert result.returncode != 0
    assert b"ValueError" in result.stderr
