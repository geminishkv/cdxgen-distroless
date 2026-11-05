"""SBOM опубликованного образа для вложений релиза: SPDX из SBOM-аттестаций BuildKit в реестре, файл на платформу.

    python3 scripts/release_sbom.py   - GHCR_IMAGE, DIGEST, VERSION, PLATFORMS; файлы - в RELEASE_OUT (.local/release)

Платформа без SBOM, документ без пакетов или без cdxgen нужной версии - отказ, а не пустое вложение."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("RELEASE_OUT") or ROOT / ".local" / "release")
NAME = "cdxgen-distroless-{version}-{platform}.spdx.json"


def platforms(raw: str) -> list[str]:
    """Список платформ из PLATFORMS: через запятую, пробелы вокруг не значимы; пустой список - ошибка."""
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if not items or any(" " in item or "/" not in item for item in items):
        sys.exit(f"PLATFORMS должен быть списком вида linux/amd64,linux/arm64, получено: {raw!r}")
    return items


def path(version: str, platform: str) -> Path:
    return OUT / NAME.format(version=version, platform=platform.replace("/", "-"))


def documents(raw: str, wanted: list[str], version: str) -> dict[str, dict]:
    """SPDX по платформам из вывода imagetools inspect --format '{{ json .SBOM }}'."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as error:
        sys.exit(f"SBOM: вывод imagetools inspect не JSON ({error})")
    if len(wanted) == 1 and isinstance(data, dict) and "SPDX" in data:
        data = {wanted[0]: data}  # у одноплатформенного образа ключа платформы нет
    result = {}
    for platform in wanted:
        entry = data.get(platform) if isinstance(data, dict) else None
        document = entry.get("SPDX") if isinstance(entry, dict) else None
        packages = document.get("packages") if isinstance(document, dict) else None
        if not packages:
            sys.exit(f"SBOM {platform}: в аттестациях образа нет SPDX-документа с пакетами")
        if not any(package.get("name") == "@cyclonedx/cdxgen" and package.get("versionInfo") == version for package in packages):
            sys.exit(f"SBOM {platform}: среди {len(packages)} пакетов нет @cyclonedx/cdxgen {version}")
        result[platform] = document
    return result


def main() -> int:
    image, digest, version = os.environ["GHCR_IMAGE"], os.environ["DIGEST"], os.environ["VERSION"]
    wanted = platforms(os.environ["PLATFORMS"])
    try:
        done = subprocess.run(["docker", "buildx", "imagetools", "inspect", f"{image}@{digest}", "--format", "{{ json .SBOM }}"],
                              capture_output=True, text=True, check=False)
    except FileNotFoundError:
        sys.exit("imagetools inspect: docker не найден в PATH")
    if done.returncode:
        sys.exit(f"imagetools inspect: код возврата {done.returncode}\n{done.stderr[-2000:]}")
    OUT.mkdir(parents=True, exist_ok=True)
    for platform, document in documents(done.stdout, wanted, version).items():
        target = path(version, platform)
        target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"sbom {platform}: {document.get('spdxVersion')}, пакетов {len(document['packages'])}, "
              f"{target.name}, {target.stat().st_size} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
