#!/usr/bin/env python3
"""Opt in to downloading exact proceedings editions used by the figure recipes.

Unlike render.py, this utility uses the network, and only for missing papers.
It never replaces a pre-existing PDF. Approved downloads are published to the
requested directory only after the complete bytes match the recipe SHA-256.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SPECS = Path(__file__).resolve().with_name("specs")
CHUNK = 1024 * 1024


def source_catalog(specs=SPECS):
    papers = {}
    for path in sorted(specs.glob("*.json")):
        spec = json.loads(path.read_text(encoding="utf-8"))
        match = re.fullmatch(r"([a-z0-9]+)_fig[0-9]+", spec["id"])
        if not match or path.stem != spec["id"]:
            raise ValueError(f"unexpected recipe identifier in {path.name}")
        slug = match[1]
        edition = (spec["url"], spec["sha256"])
        url = urlsplit(edition[0])
        if url.scheme != "https" or not url.hostname or not re.fullmatch(r"[0-9a-f]{64}", edition[1]):
            raise ValueError(f"invalid pinned edition in {path.name}")
        if edition != papers.setdefault(slug, edition):
            raise ValueError(f"recipes for {slug} disagree about the source edition")
    if not papers:
        raise ValueError("no installed recipes")
    return papers


def check_existing(target, expected):
    if target.is_symlink() or not target.is_file():
        raise ValueError(f"{target}: existing path is not a regular, non-symlink PDF; left untouched")
    with target.open("rb") as file:
        digest = hashlib.sha256()
        for chunk in iter(lambda: file.read(CHUNK), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f"{target}: wrong SHA-256; existing file left untouched")
    return "verified existing"


def fetch_one(slug, edition, folder, opener=urlopen):
    url, expected = edition
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (slug + ".pdf")
    if target.exists() or target.is_symlink():
        return check_existing(target, expected)
    # Destination-local temporary file, so installing an already verified file
    # with link(2) is atomic and cannot replace an intervening user's file.
    with tempfile.NamedTemporaryFile(prefix=f".{slug}-", suffix=".part", dir=folder) as part:
        request = Request(
            url, headers={"User-Agent": "FigureFlow paper-rebuilds/1", "Accept": "application/pdf"}
        )
        digest = hashlib.sha256()
        with opener(request, timeout=60) as response:
            for chunk in iter(lambda: response.read(CHUNK), b""):
                digest.update(chunk)
                part.write(chunk)
        if digest.hexdigest() != expected:
            raise ValueError(f"{slug}: downloaded bytes do not match SHA-256 {expected}; nothing installed")
        part.flush()
        os.fsync(part.fileno())
        try:
            os.link(part.name, target)
        except FileExistsError:
            return check_existing(target, expected)
    return "downloaded and verified"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--list", action="store_true", help="list paper IDs, digests and URLs without network access"
    )
    selection.add_argument("--paper", help="one paper ID, as shown by --list")
    selection.add_argument(
        "--all", action="store_true", help="all unique PDFs referenced by installed recipes"
    )
    parser.add_argument("--source-dir", type=Path, help="required destination for downloads")
    args = parser.parse_args()
    try:
        papers = source_catalog()
        if args.list:
            for slug, (url, sha) in papers.items():
                print(f"{slug}\t{sha}\t{url}")
            return
        if not args.source_dir:
            parser.error("--source-dir is required; the renderer never downloads automatically")
        if args.paper and args.paper not in papers:
            parser.error(f"unknown paper ID {args.paper!r}; run --list")
        for slug in [args.paper] if args.paper else papers:
            print(f"{slug}: {fetch_one(slug, papers[slug], args.source_dir.expanduser())}", flush=True)
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
