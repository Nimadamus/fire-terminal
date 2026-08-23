"""Generate the legal pages of the website from docs/LEGAL.md.

One source, two outputs. The documents a customer reads on the website and the
documents we review with a lawyer must be the same text, and the only reliable
way to guarantee that is to generate one from the other.

    python site/build_legal.py
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "LEGAL.md"
OUT = ROOT / "site" / "legal"

# Heading in LEGAL.md -> (url slug, page title)
PAGES = {
    "1. Risk disclosure": ("risk", "Risk disclosure"),
    "2. Licence agreement": ("licence", "Licence agreement"),
    "3. Privacy policy": ("privacy", "Privacy policy"),
    "4. Refunds and cancellation": ("refunds", "Refunds and cancellation"),
    "5. Terms of service": ("terms", "Terms of service"),
    "6. Independence statement": ("independence", "Independence statement"),
}

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — FIRE</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<link rel="stylesheet" href="../style.css">
<style>
  .doc {{ max-width: 76ch; }}
  .doc p {{ color: var(--text-dim); }}
  .doc li {{ color: var(--text-dim); margin-bottom: 8px; }}
  .doc strong {{ color: var(--text); }}
  .doc blockquote {{
    border-left: 3px solid var(--accent); margin: 22px 0; padding: 6px 20px;
    color: var(--text-dim);
  }}
  .updated {{ color: var(--text-faint); font-size: 14px; margin-bottom: 30px; }}
</style>
</head>
<body>
<header>
  <div class="wrap bar">
    <div class="logo">FI<span>RE</span></div>
    <nav><a href="/">Home</a><a href="/#pricing">Pricing</a></nav>
  </div>
</header>
<section style="padding-top:56px">
  <div class="wrap doc">
    <h1 style="font-size:34px">{title}</h1>
    <p class="updated">Version {version}</p>
{body}
    <p style="margin-top:44px"><a href="/">Back to FIRE</a></p>
  </div>
</section>
</body>
</html>
"""


def render(markdown: str) -> str:
    """A deliberately small markdown subset: paragraphs, bullets, quotes, bold."""
    out: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if in_list:
                out.append("    </ul>")
                in_list = False
            continue
        if line.strip() == "---":
            continue

        text = html.escape(line.strip())
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)

        if text.startswith("&gt; "):
            out.append(f"    <blockquote>{text[5:]}</blockquote>")
        elif text.startswith("* "):
            if not in_list:
                out.append("    <ul>")
                in_list = True
            out.append(f"      <li>{text[2:]}</li>")
        else:
            if in_list:
                out.append("    </ul>")
                in_list = False
            out.append(f"    <p>{text}</p>")
    if in_list:
        out.append("    </ul>")
    return "\n".join(out)


def main() -> int:
    source = SOURCE.read_text(encoding="utf-8")
    version = "2026-08-1"
    sections = re.split(r"^## ", source, flags=re.M)[1:]
    OUT.mkdir(parents=True, exist_ok=True)

    written = 0
    for section in sections:
        heading, _, body = section.partition("\n")
        match = next((v for k, v in PAGES.items() if heading.startswith(k)), None)
        if match is None:
            continue
        slug, title = match
        page = TEMPLATE.format(title=html.escape(title), version=version,
                               body=render(body))
        (OUT / f"{slug}.html").write_text(page, encoding="utf-8")
        written += 1

    missing = len(PAGES) - written
    print(f"wrote {written} legal pages to {OUT}")
    if missing:
        print(f"WARNING: {missing} expected sections were not found in LEGAL.md")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
