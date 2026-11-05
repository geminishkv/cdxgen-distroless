"""gitleaks по всей истории репозитория; гейтящий слой: любая находка — отказ. Исключения — только .gitleaks.toml:
комментарии gitleaks:allow в коде не действуют. Неполный клон и пустой отчёт — отказ, а не «чисто»."""
from __future__ import annotations

import json

import common


def parse(report: list[dict]) -> list[dict[str, str]]:
    return [common.item("HIGH", r.get("RuleID", ""), f"{r.get('File')}:{r.get('StartLine')} @ {(r.get('Commit') or '')[:8]}",
                        "ротировать секрет, затем allowlist по коммиту и пути с причиной и сроком") for r in report]


def main() -> int:
    common.OUT.mkdir(parents=True, exist_ok=True)
    out = common.OUT / "gitleaks.raw.json"
    commits = common.run(["git", "rev-list", "--count", "HEAD"], capture=True).stdout.strip()
    common.require_count("коммитов", int(commits or 0))
    if common.run(["git", "rev-parse", "--is-shallow-repository"], capture=True).stdout.strip() == "true":
        common.die("клон неполный (shallow): история не проверяется, нужен fetch-depth: 0")
    common.run([common.tool("gitleaks"), "git", "--no-banner", "--redact", "--ignore-gitleaks-allow", "--exit-code", "0",
                "--report-format", "json", "--report-path", str(out), "."])
    report = out.read_text(encoding="utf-8") if out.is_file() else ""
    if not report.strip():
        common.die("gitleaks не записал отчёт: сканер не отработал")
    findings = parse(json.loads(report))
    status = "failure" if findings else "success"
    common.summary("gitleaks", status, {"commits": int(commits), "allowlist": ".gitleaks.toml"}, findings)
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
