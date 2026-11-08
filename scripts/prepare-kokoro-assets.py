#!/usr/bin/env python3
"""Build-time-only download/copy of pinned Kokoro files and license notices."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import tempfile
import urllib.request
from pathlib import Path


def prepare(manifest: Path, output: Path, cache: Path | None) -> None:
    data = json.loads(manifest.read_text())
    expected = {"config.json", "kokoro-v1_0.pth", "voices/af_heart.pt"}
    if set(data["files"]) != expected:
        raise ValueError("Unexpected model asset inventory")
    output.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() for p in (output, *output.parents)):
        raise ValueError("Asset output cannot be a symlink")
    for name, metadata in data["files"].items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise ValueError("Asset output cannot be a symlink")
        cached = cache / name if cache is not None else None
        if cached is not None and cached.exists():
            source = cached.open("rb")
        else:
            if not metadata["url"].startswith(
                "https://huggingface.co/hexgrad/Kokoro-82M/resolve/" + data["revision"] + "/"
            ):
                raise ValueError("Asset source is not pinned")
            source = urllib.request.urlopen(metadata["url"], timeout=120)
        temporary = None
        try:
            digest, size = hashlib.sha256(), 0
            with source, tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                while block := source.read(1024 * 1024):
                    size += len(block)
                    if size > metadata["size"]:
                        raise ValueError("Asset exceeds expected size")
                    digest.update(block)
                    stream.write(block)
            if size != metadata["size"] or digest.hexdigest() != metadata["sha256"]:
                raise ValueError("Pinned asset integrity check failed")
            os.replace(temporary, target)
            temporary = None
            target.chmod(0o644)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    shutil.copyfile(manifest, output / "manifest.json")


def licenses(output: Path) -> None:
    """Retain installed distribution notices, including bundled GPL components."""
    inventory = {}
    for distribution in importlib.metadata.distributions():
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", distribution.metadata["Name"])
        notices = []
        for entry in distribution.files or []:
            if not any(
                word in str(entry).lower() for word in ("license", "copying", "notice", "copyright")
            ):
                continue
            source = Path(str(distribution.locate_file(entry)))
            if source.is_file() and source.stat().st_size <= 1024 * 1024:
                target = output / "licenses" / name / re.sub(r"[^A-Za-z0-9_.-]", "_", str(entry))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                notices.append(target.relative_to(output).as_posix())
        inventory[name] = {"version": distribution.version, "notices": notices}
    (output / "package-notices.json").write_text(json.dumps(inventory, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--include-package-licenses", action="store_true")
    args = parser.parse_args()
    prepare(args.manifest, args.output_dir, args.cache_dir)
    if args.include_package_licenses:
        licenses(args.output_dir)
    print("Pinned Kokoro assets prepared; runtime downloads are unnecessary.")


if __name__ == "__main__":
    main()
