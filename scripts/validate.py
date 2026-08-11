#!/usr/bin/env python3
"""Fail-closed checks for the manifest and the rendered output.

Two independent gates:

1. The manifest is a closed key allowlist with bounded integer values.
   "Integers only" would not be enough on its own -- a ZIP code, a phone
   number and a coordinate are all integers -- so the key set is closed and
   the ranges are narrow.

2. Every text node in the generated SVG must be a value this repository
   intends to publish. This is an allowlist, not a denylist, on purpose: a
   denylist committed to a public repository would publish the very strings
   it exists to suppress, and it can only catch leaks somebody predicted.
"""

import json
import pathlib
import re
import sys
from xml.etree import ElementTree

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import render  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "system.json"
SVG_NS = "http://www.w3.org/2000/svg"

ALLOWED_KEYS = {
    "enforcement_handlers": (0, 10000),
    "lifecycle_events": (0, 64),
    "scheduled_jobs": (0, 10000),
    "memory_entries": (0, 10000),
    "skills": (0, 10000),
}

LIVE_LINE = re.compile(
    r"^generated \d{4}-\d{2}-\d{2}"
    r"( · \d{1,4} public (repository|repositories))?$"
)


class Failure(Exception):
    pass


def check_manifest(values: object) -> None:
    if not isinstance(values, dict):
        raise Failure("manifest is not an object")

    unknown = set(values) - set(ALLOWED_KEYS)
    if unknown:
        raise Failure(f"unknown key(s) rejected: {sorted(unknown)}")

    missing = set(ALLOWED_KEYS) - set(values)
    if missing:
        raise Failure(f"missing key(s): {sorted(missing)}")

    for key, (lo, hi) in ALLOWED_KEYS.items():
        v = values[key]
        # bool is a subclass of int in Python; reject it explicitly.
        if isinstance(v, bool) or not isinstance(v, int):
            raise Failure(f"{key}: value must be an integer, got {type(v).__name__}")
        if not lo <= v <= hi:
            raise Failure(f"{key}: {v} outside allowed range {lo}-{hi}")

    print(f"manifest ok: {len(values)} keys, all bounded integers")


def build_vocabulary(values: dict[str, int]) -> set[str]:
    vocab = {render.NAME, render.TAGLINE, render.BOUNDARY}
    for label, _key, unit, qualifier, _meter, principle in render.MODULES:
        vocab.update({label, unit, qualifier, principle})
    vocab.update(str(v) for v in values.values())
    return vocab


def check_svg(path: pathlib.Path, vocab: set[str]) -> None:
    tree = ElementTree.parse(path)

    for el in tree.iter():
        for attr, val in el.attrib.items():
            if attr == "{http://www.w3.org/XML/1998/namespace}space":
                continue
            if re.search(r"https?://|//", val):
                raise Failure(f"{path.name}: external reference in @{attr}: {val}")

    strings = []
    for el in tree.iter():
        if el.tag == f"{{{SVG_NS}}}text" and el.text:
            strings.append(el.text.strip())
    for el in tree.iter():
        label = el.get("aria-label")
        if label:
            strings.append(label)

    if not strings:
        raise Failure(f"{path.name}: no text nodes found -- renderer changed shape")

    for s in strings:
        if not s or s in vocab or LIVE_LINE.match(s):
            continue
        if s == f"{render.NAME} — {render.TAGLINE}":
            continue
        raise Failure(f"{path.name}: string not in allowlist: {s!r}")

    print(f"{path.name} ok: {len(strings)} strings, all in allowlist")


# Advance width per character as a fraction of font-size. Monospace faces sit
# at 0.60em; the sans numerals are wider but only ever hold short strings.
MONO_ADVANCE = 0.60
SANS_ADVANCE = 0.62


def check_bounds(path: pathlib.Path) -> None:
    """Reject text that runs outside the canvas.

    Copy edits are the likely future change to this repo, and an overlong
    qualifier would silently clip on the right edge rather than fail.
    """
    tree = ElementTree.parse(path)
    root = tree.getroot()
    width = float(root.get("width", "0"))
    right_limit = width - render.MARGIN + 1  # +1 absorbs rounding

    for el in tree.iter():
        if el.tag != f"{{{SVG_NS}}}text" or not el.text:
            continue
        size = float(el.get("font-size", "11"))
        family = el.get("font-family", "")
        advance = SANS_ADVANCE if family.startswith("ui-sans") else MONO_ADVANCE
        spacing = float(el.get("letter-spacing", "0"))
        text = el.text.strip()
        est = len(text) * (size * advance + spacing)
        x = float(el.get("x", "0"))
        left = x - est if el.get("text-anchor") == "end" else x
        right = left + est
        if right > right_limit:
            raise Failure(
                f"{path.name}: text overflows canvas by {right - right_limit:.0f}px: {text!r}"
            )
        if left < render.MARGIN - 1:
            raise Failure(f"{path.name}: text starts left of the margin: {text!r}")

    print(f"{path.name} ok: all text within {render.MARGIN}px margins")


def main() -> int:
    try:
        values = json.loads(MANIFEST.read_text())
        check_manifest(values)
        vocab = build_vocabulary(values)
        for name in ("banner-dark.svg", "banner-light.svg"):
            check_svg(ROOT / "assets" / name, vocab)
            check_bounds(ROOT / "assets" / name)
    except Failure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
