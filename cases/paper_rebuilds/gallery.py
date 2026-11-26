"""Build the offline review index after the batch renderer produces local assets."""

from __future__ import annotations

import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

CSS = """
:root{color-scheme:light;--ink:#193438;--muted:#476166;--accent:#005e56;--line:#cbd9d6}
*{box-sizing:border-box}
body{margin:0;background:#f3f6f4;color:var(--ink);font:16px/1.55 system-ui,sans-serif}
main{max-width:1540px;margin:0 auto;padding:30px clamp(12px,3vw,52px) 60px}
h1,h2,p,figure{margin:0}
h1{font-size:clamp(26px,4.5vw,48px);line-height:1.2;margin:5px 0 10px;letter-spacing:-.035em}
h2{font-size:clamp(21px,2.4vw,28px);line-height:1.25;letter-spacing:-.02em}
header>p,article>p{max-width:100ch}
.eyebrow,figcaption{font-size:12px;letter-spacing:.085em;text-transform:uppercase;font-weight:700;color:var(--accent)}
a{color:#005952;text-underline-offset:3px}
a:focus-visible{outline:3px solid #ba7109;outline-offset:3px}
nav{display:flex;flex-wrap:wrap;gap:5px 16px;padding:16px 0 4px}
nav a{font-size:14px}
article{background:#fff;border:1px solid var(--line);margin:22px 0 0;padding:clamp(12px,2vw,26px);scroll-margin-top:1em}
article header{display:flex;gap:8px;align-items:baseline;flex-wrap:wrap;justify-content:space-between}
.location{color:var(--muted);font-size:14px}
.claim{margin-top:.45em}
.pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:17px 0}
figure{min-width:0;border-top:2px solid var(--ink);padding-top:5px}
figure a{display:block}
figure img{display:block;width:100%;height:auto;margin-top:8px}
.swatches,.links{display:flex;flex-wrap:wrap;gap:.4em 1.2em;margin:10px 0;align-items:center}
.swatch{display:inline-flex;gap:.4em;align-items:center;color:var(--muted);font-size:13px}
.swatch i{width:14px;height:14px;display:inline-block;border:1px solid #697e7a}
code{color:var(--ink);user-select:all}
.note{font-size:14px;color:var(--muted);margin:10px 0 0}
@media(max-width:720px){main{padding-top:18px}.pair{grid-template-columns:1fr;gap:15px}article{margin-top:14px}}
@media print{body{background:white}nav,.links{display:none}main{padding:0}article{break-inside:avoid}}
"""


def write_gallery(specs, output_dir):
    """Write index.html. All display assets and file links are local and relative."""
    out = Path(output_dir)
    nav, cards, ids = [], [], set()
    for s in specs:
        key = s["id"]
        if not re.fullmatch(r"[a-z0-9_]+", key) or key in ids:
            raise ValueError(f"invalid or duplicate gallery id: {key!r}")
        ids.add(key)
        title = escape(f"{s['paper']} · {s['figure']}")
        venue, page = escape(str(s["venue"])), escape(str(s["page"]))
        url = urlsplit(s["url"])
        if url.scheme != "https" or not url.netloc:
            raise ValueError(f"source link must be an absolute HTTPS URL: {key}")
        source = escape(s["url"], quote=True)
        nav.append(f'<a href="#{key}">{title}</a>')
        frames = []
        for label, path in (
            ("论文原图 / Original", "reference.png"),
            ("分层复刻 / Reconstruction", "candidate.png"),
        ):
            frames.append(
                f'<figure><figcaption>{label}</figcaption><a href="{key}/{path}" '
                f'aria-label="放大 {title} · {label}"><img loading="lazy" '
                f'src="{key}/{path}" alt="{title} · {label}"></a></figure>'
            )
        swatches = []
        for name, color in s["palette"].items():
            if not re.fullmatch(r"#[a-fA-F0-9]{6}", color):
                raise ValueError(f"expected #RRGGBB in palette: {key}")
            swatches.append(
                f'<span class="swatch"><i aria-hidden="true" style="background:{color}"></i>'
                f"{escape(name.replace('_', ' '))} <code>{color.upper()}</code></span>"
            )
        links = " ".join(
            f'<a href="{key}/{file}">{name}</a>'
            for name, file in [
                ("可编辑 SVG", "candidate.svg"),
                ("TikZ 源文件", "candidate_tikz.tex"),
                ("复刻 PDF", "candidate.pdf"),
                ("对照 PDF", "comparison.pdf"),
                ("素材来源", "provenance.json"),
            ]
        )
        limits = s["limitations"]
        limit = limits if isinstance(limits, str) else " ".join(limits)
        cards.append(
            f'<article id="{key}"><header><h2>{title}</h2>'
            f'<span class="location">{venue} · PDF p. {page}</span></header>'
            f'<p class="claim">{escape(s["claim"])}</p><div class="pair">{"".join(frames)}</div>'
            f'<div class="swatches" aria-label="图中配色">{"".join(swatches)}</div>'
            f'<div class="links">{links} <a href="{source}">论文来源（联网）</a></div>'
            f'<p class="note"><b>还原边界：</b>{escape(limit)}</p></article>'
        )
    page = (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>FigureFlow · 原图与复刻</title><style>" + CSS + "</style></head><body><main>"
        '<header><p class="eyebrow">FigureFlow / Reconstruction review</p><h1>原图与复刻</h1>'
        f"<p>{len(cards)} 张图按相同比例并排。点击图片可放大；色号可直接选取复制。"
        "案例和数据来自原论文，不代表重新运行了实验。</p></header>"
        + '<nav aria-label="跳转至论文图">'
        + "".join(nav)
        + "</nav>"
        + "".join(cards)
        + "</main></body></html>"
    )
    out.mkdir(parents=True, exist_ok=True)
    target = out / "index.html"
    target.write_text(page, encoding="utf-8")
    return target
