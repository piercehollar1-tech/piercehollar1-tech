#!/usr/bin/env python3
"""Render the profile banner SVGs from the manifest plus public GitHub data.

Standard library only, deliberately: no third-party runtime dependency to
compromise, and no `pip install` step in CI.

The GitHub query is sent UNAUTHENTICATED. The /users/{owner}/repos endpoint
cannot return private repositories to an anonymous caller, so a private
repository name cannot reach this renderer even if the rest of the filtering
were wrong. This is a structural control, not a careful one.
"""

import json
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import date
from xml.sax.saxutils import escape

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "system.json"
ASSETS = ROOT / "assets"
OWNER = "piercehollar1-tech"

W, H = 880, 272
MARGIN = 48
COLS = (48, 246, 444, 642)
DIVIDERS = (228, 426, 624)

SANS = "ui-sans-serif,-apple-system,'Helvetica Neue',Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,monospace"

NAME = "Pierce Hollar"
TAGLINE = "applied AI · I build the tooling I work inside"
BOUNDARY = "figures describe the shape of a private system, never its contents"

# label, manifest key, unit, qualifier, meter, principle
MODULES = (
    ("ENFORCEMENT", "enforcement_handlers", "handlers",
     "across 8 lifecycle events", "ticks", "blocks, does not advise"),
    ("SCHEDULED", "scheduled_jobs", "jobs",
     "retry and catch-up runs", "dots", "idempotent by marker"),
    ("MEMORY", "memory_entries", "entries",
     "hot index, cold archive", "rule", "retrieved on demand"),
    ("WORKFLOWS", "skills", "skills",
     "review-gated by default", "rule", "procedure, not facts"),
)

# Every colour carrying 11px text is held at >=4.5:1 against its background.
# The first pass used #46515F on near-black, which measured 3.3:1 and is not
# readable at this size.
DARK = {
    "bg": "#0B0E14", "dot": "#1A2230", "rule": "#1C2532", "dim_rule": "#2A3646",
    "text": "#E6EDF3", "muted": "#8B98AD", "dim": "#8792A1", "faint": "#7B8592",
    "accent": "#F2A93B",
}
LIGHT = {
    "bg": "#FBFBFA", "dot": "#E4E7EB", "rule": "#DFE3E8", "dim_rule": "#C4CBD4",
    "text": "#16202C", "muted": "#4E5A69", "dim": "#5A6472", "faint": "#626C79",
    "accent": "#A66300",
}


def txt(x: float, y: float, s: str, *, family: str = MONO, size: int = 11,
        fill: str = "#000", weight: str | None = None,
        spacing: float | None = None, anchor: str | None = None) -> str:
    attrs = [f'x="{x}"', f'y="{y}"', f'font-family="{family}"',
             f'font-size="{size}"', f'fill="{fill}"']
    if weight:
        attrs.append(f'font-weight="{weight}"')
    if spacing is not None:
        attrs.append(f'letter-spacing="{spacing}"')
    if anchor:
        attrs.append(f'text-anchor="{anchor}"')
    return f'  <text {" ".join(attrs)}>{escape(s)}</text>'


def render(values: dict[str, int], live_line: str, p: dict[str, str]) -> str:
    o = [
        f'<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}" role="img" aria-label="'
        f'{escape(NAME)} — {escape(TAGLINE)}">',
        '  <defs>',
        '    <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">',
        f'      <circle cx="0.5" cy="0.5" r="0.5" fill="{p["dot"]}"/>',
        '    </pattern>',
        '  </defs>',
        f'  <rect width="{W}" height="{H}" fill="{p["bg"]}"/>',
        f'  <rect width="{W}" height="{H}" fill="url(#dots)"/>',
        f'  <rect x="{MARGIN}" y="30" width="3" height="42" fill="{p["accent"]}"/>',
    ]
    o.append(txt(64, 58, NAME, family=SANS, size=31, fill=p["text"],
                 weight="600", spacing=-0.6))
    o.append(txt(64, 80, TAGLINE, size=12, fill=p["muted"], spacing=0.3))
    o.append(f'  <line x1="{MARGIN}" y1="104" x2="{W - MARGIN}" y2="104" '
             f'stroke="{p["rule"]}"/>')

    for i, (label, key, unit, qualifier, meter, principle) in enumerate(MODULES):
        x = COLS[i]
        value = values[key]
        accent = p["accent"] if i == 0 else p["text"]
        o.append(txt(x, 134, label, size=11, fill=p["dim"], spacing=1.3))
        o.append(txt(x, 172, str(value), family=SANS, size=30,
                     fill=accent, weight="600"))
        o.append(txt(x + 12 + 18 * len(str(value)), 172, unit, size=11,
                     fill=p["muted"]))
        o.append(txt(x, 191, qualifier, size=11, fill=p["muted"]))

        if meter == "ticks":
            for t in range(values["lifecycle_events"]):
                tx = x + t * 13
                o.append(f'  <rect x="{tx}" y="203" width="7" height="6" '
                         f'fill="{p["accent"]}"/>')
        elif meter == "dots":
            for d in range(value):
                o.append(f'  <circle cx="{x + 5 + d * 15}" cy="206" r="3.5" '
                         f'fill="{p["accent"]}"/>')
        else:
            o.append(f'  <line x1="{x}" y1="206" x2="{x + 96}" y2="206" '
                     f'stroke="{p["dim_rule"]}" stroke-width="2"/>')

        o.append(txt(x, 228, principle, size=11, fill=p["faint"], spacing=0.3))

    o.append(txt(MARGIN, 256, BOUNDARY, size=11, fill=p["faint"], spacing=0.2))
    o.append(txt(W - MARGIN, 256, live_line, size=11, fill=p["faint"],
                 spacing=0.2, anchor="end"))
    o.append('</svg>')
    return "\n".join(o) + "\n"


def public_repo_count(owner: str) -> int:
    """Anonymous request. Cannot see private repositories by construction."""
    req = urllib.request.Request(
        f"https://api.github.com/users/{owner}/repos?type=owner&per_page=100",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "profile-banner-renderer"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return len(json.load(resp))


def main() -> int:
    values = json.loads(MANIFEST.read_text())
    today = date.today().isoformat()

    try:
        n = public_repo_count(OWNER)
        noun = "repository" if n == 1 else "repositories"
        live_line = f"generated {today} · {n} public {noun}"
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        # Degrade rather than fail: a slightly stale banner beats a broken one.
        print(f"live data unavailable, rendering from manifest only: {type(exc).__name__}")
        live_line = f"generated {today}"

    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "banner-dark.svg").write_text(render(values, live_line, DARK))
    (ASSETS / "banner-light.svg").write_text(render(values, live_line, LIGHT))
    print(f"rendered 2 variants · {live_line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
