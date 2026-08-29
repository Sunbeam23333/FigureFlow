#!/usr/bin/env python3
"""Batch-compile standalone TeX figures and render review PNGs."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path


def discover_sources(items: list[str], pattern: str) -> list[Path]:
    sources: list[Path] = []
    for raw in items:
        path = Path(raw).expanduser().resolve()
        if path.is_dir():
            candidates = sorted(path.rglob(pattern))
            sources.extend(
                candidate
                for candidate in candidates
                if "\\documentclass" in candidate.read_text(encoding="utf-8", errors="ignore")
            )
        elif path.suffix.lower() == ".tex":
            sources.append(path)
        else:
            raise FileNotFoundError(f"Not a TeX file or directory: {path}")
    return sorted(dict.fromkeys(sources))


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=180,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", help="TeX files or directories")
    parser.add_argument("--pattern", default="*.tex", help="Recursive file pattern")
    parser.add_argument("--output-dir", type=Path, default=Path("rendered"))
    parser.add_argument("--engine", default="xelatex")
    parser.add_argument("--dpi", type=int, default=220)
    parser.add_argument("--no-png", action="store_true")
    args = parser.parse_args()

    engine = shutil.which(args.engine)
    if not engine:
        print(f"error: TeX engine not found: {args.engine}", file=sys.stderr)
        return 2
    renderer = shutil.which("pdftoppm")
    if not args.no_png and not renderer:
        print("error: pdftoppm is required for PNG rendering", file=sys.stderr)
        return 2

    try:
        sources = discover_sources(args.inputs, args.pattern)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not sources:
        print("error: no TeX sources found", file=sys.stderr)
        return 2

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    failed = 0

    stem_counts = {stem: sum(item.stem == stem for item in sources) for stem in {item.stem for item in sources}}
    for source in sources:
        suffix = hashlib.sha1(str(source).encode("utf-8")).hexdigest()[:8]
        output_stem = source.stem if stem_counts[source.stem] == 1 else f"{source.stem}-{suffix}"
        job_dir = output_dir / output_stem
        job_dir.mkdir(parents=True, exist_ok=True)
        result = run(
            [
                engine,
                "-interaction=nonstopmode",
                "-halt-on-error",
                f"-output-directory={job_dir}",
                source.name,
            ],
            source.parent,
        )
        pdf = job_dir / f"{source.stem}.pdf"
        log = job_dir / "compile.log"
        log.write_text(result.stdout, encoding="utf-8")
        if result.returncode != 0 or not pdf.exists():
            failed += 1
            print(f"FAIL {source} (see {log})")
            continue

        final_pdf = output_dir / f"{output_stem}.pdf"
        shutil.copy2(pdf, final_pdf)
        if not args.no_png:
            png_prefix = output_dir / output_stem
            rendered = run(
                [
                    renderer,
                    "-png",
                    "-singlefile",
                    "-r",
                    str(args.dpi),
                    str(final_pdf),
                    str(png_prefix),
                ],
                output_dir,
            )
            if rendered.returncode != 0:
                failed += 1
                print(f"FAIL render {final_pdf}: {rendered.stdout.strip()}")
                continue
        print(f"OK   {source.name} -> {final_pdf.name}")

    print(f"compiled={len(sources) - failed} failed={failed} total={len(sources)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
