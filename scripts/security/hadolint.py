"""hadolint по Dockerfile (одному или нескольким): JSON-отчёт, сводка для report.py. Падает на error и warning.
Подавления в обход ревью не действуют: прагмы hadolint ignore отключены, конфиг .hadolint.yaml в каталоге — отказ."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import common

LEVELS = {"error": "HIGH", "warning": "MEDIUM", "info": "LOW", "style": "LOW"}
CONFIGS = (".hadolint.yaml", ".hadolint.yml")


def parse(report: list[dict]) -> list[dict[str, str]]:
    return [common.item(LEVELS.get(r.get("level", ""), "UNKNOWN"), r.get("code", ""), f"{r.get('file', 'Dockerfile')}:{r.get('line', '')}",
                        (r.get("message") or "").strip()) for r in report]


def main() -> int:
    paths = sys.argv[1:] or ["Dockerfile"]
    if config := next((name for name in CONFIGS if Path(name).exists()), None):
        common.die(f"{config}: конфиг hadolint в каталоге глушит правила и здесь не поддерживается")
    done = common.run([common.tool("hadolint"), "--format", "json", "--no-fail", "--disable-ignore-pragma", *paths], capture=True)
    findings = parse(json.loads(done.stdout or "[]"))
    common.require_count("Dockerfile", len(paths))
    blocking = [f for f in findings if f["severity"] in ("HIGH", "MEDIUM")]
    status = "failure" if blocking else "success"
    common.summary("hadolint", status, {"files": len(paths), "rules": "все правила hadolint", "hits": len(findings)}, findings)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
