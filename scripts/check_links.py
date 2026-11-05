#!/usr/bin/env python3
"""Относительные ссылки в *.md ведут на существующие файлы (якоря не проверяются).

Запускается хуком pre-commit и job lint в CI; проверяет все *.md репозитория, кроме .git, .venv, .local и
node_modules. Печатает число проверенных файлов: «ноль битых» без него не отличить от «не дошёл».
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINK = re.compile(r"\]\(([^)\s]+)\)")
SKIP_PREFIXES = ("http://", "https://", "mailto:", "#", "tel:")


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    bad: list[str] = []
    checked = 0
    for md in sorted(root.rglob("*.md")):
        if any(part in {".git", ".venv", ".local", "node_modules"} for part in md.parts):
            continue
        checked += 1
        for match in LINK.finditer(md.read_text(encoding="utf-8")):
            target = match.group(1).split("#", 1)[0]
            if not target or target.startswith(SKIP_PREFIXES):
                continue
            if not (md.parent / target).exists():
                bad.append(f"{md.relative_to(root)}: {match.group(1)}")
    for line in bad:
        print(line, file=sys.stderr)
    print(f"check_links: файлов {checked}, битых ссылок {len(bad)}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
