"""SBOM образа двумя способами: syft по образу (ОС и npm) и cdxgen из самого образа по его lock-файлу (без сети).

    python3 scripts/security/sbom.py <image-ref>

Оба CycloneDX JSON — артефакты релиза; компонентов ноль — отказ, не пустой SBOM."""
from __future__ import annotations

import sys
import uuid

import common


SPEC = "1.6"  # одна версия CycloneDX для обоих SBOM


def components(path, what: str) -> int:
    data = common.load_json(path, what)
    return common.require_count(f"{what}: компонентов", len(data.get("components") or []))


def main() -> int:
    if len(sys.argv) < 2:
        common.die("нужен образ: scripts/security/sbom.py <image>")
    image = sys.argv[1]
    common.OUT.mkdir(parents=True, exist_ok=True)
    image_bom = common.OUT / "sbom-image.cdx.json"
    self_bom = common.OUT / "sbom-cdxgen.cdx.json"
    common.run([common.tool("syft"), "scan", "--quiet", "-o", f"cyclonedx-json@{SPEC}={image_bom}", image])
    n_image = components(image_bom, "syft по образу")
    # cdxgen внутри образа читает package.json и package-lock.json репозитория: каталог только на чтение, без сети,
    # результат забирается через docker cp — на rootless docker процесс контейнера в каталог не пишет
    name = f"cdxgen-self-{uuid.uuid4().hex[:8]}"
    try:
        common.run(["docker", "create", "--name", name, "--network", "none", "-e", "HOME=/tmp", "-v", f"{common.ROOT}:/app:ro", "-w", "/app",
                    image, "-t", "js", "--spec-version", SPEC, "--no-install-deps", "-o", "/tmp/bom.json", "/app"], capture=True)
        common.run(["docker", "start", "-a", name], capture=True)
        common.run(["docker", "cp", f"{name}:/tmp/bom.json", str(self_bom)], capture=True)
    finally:
        common.run(["docker", "rm", "-f", name], check=False, capture=True)
    n_self = components(self_bom, "cdxgen по package-lock.json")
    common.summary("sbom", "success", {"image_components": n_image, "cdxgen_components": n_self, "format": f"CycloneDX {SPEC} JSON"}, [],
                   "артефакты sbom-image.cdx.json и sbom-cdxgen.cdx.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
