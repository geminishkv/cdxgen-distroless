"""Общее для скриптов гейта: пины инструментов, каталоги, сводка job'а в JSON для report.py.

Каждый скрипт печатает покрытие (что реально просканировано) и пишет <OUT>/<tool>.json; report.py собирает
эти файлы из артефактов и рендерит одну сводку. Ноль просмотренных объектов — отказ инструмента, не успех."""
from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn

ROOT = Path(__file__).resolve().parents[2]
HOME = Path(os.environ.get("SECURITY_HOME") or ROOT / ".local" / "security")  # .local/ в .gitignore
BIN = HOME / "bin"
OUT = Path(os.environ.get("SECURITY_OUT") or HOME / "reports")

VERSIONS = {"trivy": "0.76.1", "hadolint": "2.15.1", "syft": "1.55.0", "gitleaks": "8.30.1"}
REPOS = {"trivy": "aquasecurity/trivy", "hadolint": "hadolint/hadolint", "syft": "anchore/syft", "gitleaks": "gitleaks/gitleaks"}
# (инструмент, платформа) → (ассет релиза, sha256 ассета). Платформа — platform_key(): linux-x86_64, linux-aarch64, darwin-arm64.
ASSETS: dict[tuple[str, str], tuple[str, str]] = {
    ("trivy", "linux-x86_64"): ("trivy_0.76.1_Linux-64bit.tar.gz", "c7cbe3137fb8a48a17574bede3dd6beb16742d1e9772929940fc90082c39d9c0"),
    ("trivy", "darwin-arm64"): ("trivy_0.76.1_macOS-ARM64.tar.gz", "11a9b6cd2752011b54f01ea4bd0dbfa9f0c41dc6538d5a3f9d23955f471bf4e5"),
    ("hadolint", "linux-x86_64"): ("hadolint-linux-x86_64", "c7187db94eeeeca956519a6af171adc31453941a1e777961f6e680f697c8c507"),
    ("hadolint", "linux-aarch64"): ("hadolint-linux-arm64", "f6198ef8090f404dbb771abfee086eb8c48ac177f30da7fd3510aca35b344b5d"),
    ("hadolint", "darwin-arm64"): ("hadolint-macos-arm64", "5c09f3213f8e40406abe048233d985eebef336d4a6a20021be47fadb6cf480a2"),
    ("syft", "linux-x86_64"): ("syft_1.55.0_linux_amd64.tar.gz", "bb65249542db5fedeeb4d3f9b018b75e7264dbfbbb10486f044581a92f90490d"),
    ("syft", "darwin-arm64"): ("syft_1.55.0_darwin_arm64.tar.gz", "1217c258bd5eb91ef3189cf22a82e02f9cac07e4ce934350f428e93aff674625"),
    ("gitleaks", "linux-x86_64"): ("gitleaks_8.30.1_linux_x64.tar.gz", "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"),
    ("gitleaks", "darwin-arm64"): ("gitleaks_8.30.1_darwin_arm64.tar.gz", "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5"),
}
# Слой сводки → инструмент, чья версия попадает в отчёт; у остальных слоёв имя совпадает с инструментом
LAYER_TOOL = {"trivy-config": "trivy", "trivy-image": "trivy", "sbom": "syft"}
SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN")
_ALIASES = {"ERROR": "HIGH", "WARNING": "MEDIUM", "WARN": "MEDIUM", "INFO": "LOW", "STYLE": "LOW", "MODERATE": "MEDIUM", "NEGLIGIBLE": "LOW"}


def platform_key() -> str:
    machine = platform.machine().lower()
    machine = {"amd64": "x86_64", "aarch64": "aarch64", "arm64": "arm64" if sys.platform == "darwin" else "aarch64"}.get(machine, machine)
    return f"{sys.platform}-{machine}"


def die(message: str) -> NoReturn:
    print(f"::error::{message}" if os.environ.get("GITHUB_ACTIONS") else f"ошибка: {message}", file=sys.stderr)
    sys.exit(1)


def tool(name: str) -> str:
    """Путь к бинарю из .local/security/bin; системный — только явно (SECURITY_SYSTEM_TOOLS=1)."""
    path = BIN / name
    if path.is_file():
        return str(path)
    if os.environ.get("SECURITY_SYSTEM_TOOLS") == "1":
        return name
    die(f"{name} не установлен: python3 scripts/security/install.py {name}")


def run(cmd: list[str], *, check: bool = True, capture: bool = False, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    print("+", " ".join(cmd), flush=True)
    done = subprocess.run(cmd, check=False, capture_output=capture, text=True, env={**os.environ, **(env or {})})
    if check and done.returncode:
        if capture:  # перехваченный вывод упавшей команды иначе теряется
            sys.stderr.write((done.stderr or done.stdout or "")[-2000:])
        die(f"{Path(cmd[0]).name}: код возврата {done.returncode}")
    return done


def severity(value: Any) -> str:
    text = str(value or "").upper()
    text = _ALIASES.get(text, text)
    return text if text in SEVERITIES else "UNKNOWN"


def require_count(what: str, n: int) -> int:
    """«Ноль находок» и «сканер не дошёл до объекта» выглядят одинаково — покрытие должно быть ненулевым."""
    if n <= 0:
        die(f"{what}: 0 — инструмент ничего не проверил")
    print(f"покрытие: {what} = {n}")
    return n


def layer_version(name: str) -> str:
    return VERSIONS.get(LAYER_TOOL.get(name, name), "")


def item(sev: Any, ident: str, where: str, fix: str = "", status: str = "new") -> dict[str, str]:
    return {"severity": severity(sev), "id": ident, "where": where, "fix": fix, "status": status}


def summary(name: str, status: str, coverage: dict[str, Any], findings: list[dict[str, str]], note: str = "") -> Path:
    """Сводка job'а для report.py: статус гейта этого слоя, покрытие, находки (new / accepted / false_positive)."""
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.json"
    path.write_text(json.dumps({"tool": name, "version": layer_version(name), "status": status, "coverage": coverage,
                                "findings": findings, "note": note}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {s: sum(1 for f in findings if f["status"] == "new" and f["severity"] == s) for s in SEVERITIES}
    print(f"{name}: {status}; новых {sum(counts.values())} {dict((k, v) for k, v in counts.items() if v)}; сводка {path}")
    return path


def load_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        die(f"{what}: отчёт не читается ({error})")
