"""trivy image по собранному образу: уязвимости ОС и npm; гейт — CRITICAL и HIGH с доступным исправлением.

    python3 scripts/security/trivy_image.py <image-ref|docker-archive:путь.tar>

Baseline — .trivyignore.yaml (id, причина, срок): такие находки Trivy в отчёт не включает, гейт их не видит."""
from __future__ import annotations

import sys

import common


def parse(report: dict) -> tuple[list[dict[str, str]], dict[str, int | str]]:
    findings, packages, targets = [], {}, []
    for result in report.get("Results") or []:
        targets.append(result.get("Type", ""))
        packages[targets[-1]] = packages.get(targets[-1], 0) + len(result.get("Packages") or [])
        for v in result.get("Vulnerabilities") or []:
            fix = v.get("FixedVersion") or ""
            findings.append(common.item(v.get("Severity"), v.get("VulnerabilityID", ""), f"{v.get('PkgName')} {v.get('InstalledVersion')} ({result.get('Type')})",
                                        f"обновить до {fix}" if fix else "исправления нет"))
    os_info = report.get("Metadata", {}).get("OS") or {}
    coverage = {"targets": len(targets), "packages": sum(packages.values()), "os": f"{os_info.get('Family', '')} {os_info.get('Name', '')}".strip(),
                "os_packages": packages.get(os_info.get("Family", ""), 0), "npm_packages": packages.get("node-pkg", 0)}
    return findings, coverage


def blocking(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    return [f for f in findings if f["status"] == "new" and f["severity"] in ("CRITICAL", "HIGH") and f["fix"] != "исправления нет"]


def main() -> int:
    if len(sys.argv) < 2:
        common.die("нужен образ: scripts/security/trivy_image.py <image>")
    image = sys.argv[1]
    out = common.OUT / "trivy-image.raw.json"
    common.OUT.mkdir(parents=True, exist_ok=True)
    source = ["--input", image.removeprefix("docker-archive:")] if image.startswith("docker-archive:") else [image]
    common.run([common.tool("trivy"), "image", "--quiet", "--scanners", "vuln", "--list-all-pkgs", "--format", "json", "--output", str(out),
                "--ignorefile", ".trivyignore.yaml", *source])
    findings, coverage = parse(common.load_json(out, "trivy image"))
    common.require_count("пакетов в образе", int(coverage["packages"]))
    common.require_count("пакетов ОС", int(coverage["os_packages"]))  # слой, пропавший из отчёта, — отказ сканера
    common.require_count("пакетов npm", int(coverage["npm_packages"]))
    gate = blocking(findings)
    status = "failure" if gate else "success"
    common.summary("trivy-image", status, coverage, findings, "гейт: CRITICAL и HIGH с доступным исправлением")
    return 1 if gate else 0


if __name__ == "__main__":
    raise SystemExit(main())
