"""Версия образа = версия @cyclonedx/cdxgen из package.json. До сборки проверяется: список платформ; на теге - тег v<версия>,
непустой раздел [версия] в CHANGELOG.md и сухой рендер заметок и описания Docker Hub; ручной запуск - с основной ветки или тега.
Печатает version=<x> для $GITHUB_OUTPUT."""
import os
import sys
from pathlib import Path

import dockerhub_description
import release_notes
import release_sbom
import release_summary

ROOT = Path(__file__).resolve().parent.parent


def problem(version: str, ref_type: str, ref: str, default_branch: str, changelog: str) -> str:
    """Причина остановить релиз; пустая строка — можно собирать."""
    if ref_type == "tag":
        if ref != f"v{version}":
            return f"тег {ref} не совпадает с версией cdxgen {version} в package.json"
        if not release_notes.changelog_section(changelog, version):
            return f"в CHANGELOG.md нет раздела [{version}] или он пуст: заметки релиза собрать не из чего"
    elif ref_type == "branch" and ref != default_branch:
        return f"ручной релиз возможен только с ветки {default_branch}, запуск был с {ref}"
    return ""


def preflight(version: str, changelog: str, dockerfile: str) -> None:
    """Сухой рендер заметок и описания Docker Hub: ошибка шаблона или Dockerfile всплывает до публикации образа, а не после."""
    release_notes.notes(version, release_notes.PREVIEW_DIGEST, changelog, dockerfile, release_notes.attachments(version, require=False))
    dockerhub_description.repository()
    dockerhub_description.short(dockerfile)
    dockerhub_description.overview(version, release_notes.PREVIEW_DIGEST, dockerfile)


def main() -> int:
    version, ref_type = release_notes.package_version(), os.environ.get("GITHUB_REF_TYPE", "")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    error = problem(version, ref_type, os.environ.get("GITHUB_REF_NAME", ""), os.environ.get("DEFAULT_BRANCH") or "main", changelog)
    if error:
        sys.exit(error)
    release_sbom.platforms(release_summary.PLATFORMS)
    if ref_type == "tag":
        preflight(version, changelog, (ROOT / "Dockerfile").read_text(encoding="utf-8"))
    print(f"version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
