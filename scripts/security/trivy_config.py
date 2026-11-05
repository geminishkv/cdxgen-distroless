"""trivy config по Dockerfile (misconfiguration, CIS Docker): сводка для report.py; гейт — HIGH и CRITICAL.
Правила — встроенные в закреплённую версию trivy (без обновления набора). Исключения — только .trivyignore.yaml."""
from __future__ import annotations

import sys
from pathlib import Path

import common


def parse(report: dict) -> tuple[list[dict[str, str]], int]:
    findings, checked = [], 0
    for result in report.get("Results") or []:
        summary = result.get("MisconfSummary") or {}
        checked += sum(int(summary.get(k, 0)) for k in ("Successes", "Failures"))
        for m in result.get("Misconfigurations") or []:
            where = f"{result.get('Target', 'Dockerfile')}:{(m.get('CauseMetadata') or {}).get('StartLine', '')}"
            findings.append(common.item(m.get("Severity"), m.get("ID", ""), where, (m.get("Resolution") or m.get("Title") or "").strip()))
    return findings, checked


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "Dockerfile"
    out = common.OUT / "trivy-config.raw.json"
    common.OUT.mkdir(parents=True, exist_ok=True)
    if not Path(path).is_file():
        common.die(f"{path}: файла нет")
    if "trivy:ignore" in Path(path).read_text(encoding="utf-8"):
        common.die(f"{path}: inline-подавление trivy:ignore здесь не поддерживается, записи — в .trivyignore.yaml")
    common.run([common.tool("trivy"), "config", "--quiet", "--skip-check-update", "--format", "json", "--output", str(out),
                "--ignorefile", ".trivyignore.yaml", path])
    findings, checked = parse(common.load_json(out, "trivy config"))
    common.require_count("проверок misconfiguration", checked)
    blocking = [f for f in findings if f["severity"] in ("HIGH", "CRITICAL")]
    status = "failure" if blocking else "success"
    common.summary("trivy-config", status, {"files": 1, "checks": checked, "hits": len(findings)}, findings)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
