"""Explicit local evidence bundle for the research agent; no silent truncation."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import subprocess


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_input(path: Path) -> dict:
    from PIL import Image
    if not path.is_file() or path.stat().st_size > 25_000_000:
        raise ValueError("Model image must be a regular file no larger than 25 MB")
    with Image.open(path) as im:
        if im.width * im.height > 25_000_000:
            raise ValueError("Model image exceeds 25 megapixels")
        im.verify()
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix)
    if mime is None:
        raise ValueError("Only registered PNG/JPEG/WebP images can enter model context")
    return {"type": "input_image", "image_url": f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode(), "detail": "high"}


@dataclass
class Source:
    id: str
    path: Path
    pages: list[str]
    sha256: str
    citation: str


class ContextBundle:
    def __init__(self, paths: list[Path], *, citations: dict[str, str] | None = None,
                 max_characters: int = 1_600_000):
        if not paths or len(paths) > 12:
            raise ValueError("Provide between one and twelve explicit source files")
        self.sources = []
        for i, given in enumerate(paths):
            path = Path(given).resolve(strict=True)
            if not path.is_file() or path.stat().st_size > 100_000_000:
                raise ValueError("Source must be a bounded regular file")
            if path.suffix.lower() == ".pdf":
                text = subprocess.run(["pdftotext", "-layout", str(path), "-"], check=True,
                                      capture_output=True, text=True, timeout=90).stdout
                pages = text.split("\f")
                if pages and not pages[-1].strip():
                    pages.pop()
            elif path.suffix.lower() in {".md", ".txt", ".tex", ".py", ".json", ".yaml", ".yml", ".csv"}:
                pages = [path.read_text(encoding="utf-8")]
            else:
                raise ValueError("Unsupported source type; provide PDF or explicit text/code evidence")
            self.sources.append(Source(f"S{i+1}", path, pages, digest(path), (citations or {}).get(path.name, path.name)))
        self.characters = sum(len(page) for s in self.sources for page in s.pages)
        if self.characters > max_characters:
            raise ValueError("Evidence exceeds configured context budget; no text was silently truncated")
        self.by_id = {s.id: s for s in self.sources}

    def manifest(self) -> list[dict]:
        return [{"id": s.id, "name": s.path.name, "sha256": s.sha256, "pages": len(s.pages),
                 "characters": sum(map(len, s.pages)), "citation": s.citation} for s in self.sources]

    def full_text(self) -> str:
        return "\n\n".join(f"<source_data id='{s.id}' name='{html.escape(s.path.name, quote=True)}' page='{i+1}'>\n{page}\n</source_data>"
                            for s in self.sources for i, page in enumerate(s.pages))

    def page(self, source_id: str, page: int, output: Path) -> Path:
        source = self.by_id[source_id]
        if not isinstance(page, int) or not 1 <= page <= len(source.pages):
            raise ValueError("Page outside the registered source")
        if source.path.suffix.lower() != ".pdf":
            raise ValueError("Page images are only available for PDF sources")
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-scale-to", "2000",
                        "-png", str(source.path), str(output.with_suffix(""))],
                       check=True, capture_output=True, timeout=90)
        return output

    def search(self, query: str, *, limit: int = 8) -> list[dict]:
        if not query.strip() or len(query) > 300:
            raise ValueError("Search requires a short literal phrase")
        results = []
        for source in self.sources:
            for page, text in enumerate(source.pages, 1):
                index = text.casefold().find(query.casefold())
                if index >= 0:
                    results.append({"source_id": source.id, "page": page,
                                    "excerpt": text[max(0, index-300):index+1000]})
                    if len(results) >= min(limit, 20):
                        return results
        return results

    def verify_quote(self, source_id: str, page: int, quote: str) -> bool:
        import re
        import unicodedata
        def normalize(value):
            value = unicodedata.normalize("NFKC", value).replace("\u00ad", "")
            value = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", value)
            return re.sub(r"\s+", " ", value).strip()
        source = self.by_id[source_id]
        return bool(quote.strip()) and 1 <= page <= len(source.pages) and normalize(quote) in normalize(source.pages[page-1])

    def save_manifest(self, path: Path):
        path.write_text(json.dumps(self.manifest(), ensure_ascii=False, indent=2), encoding="utf-8")
