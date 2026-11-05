"""Заметки и GitHub Release тега: текст - шаблон scripts/templates/release_notes.md, вложения - схемы и SBOM образа.

    python3 scripts/release_notes.py render    - напечатать заметки; без VERSION и DIGEST - предпросмотр с нулевым digest
    python3 scripts/release_notes.py publish   - Release тега GITHUB_REF_NAME с вложениями (VERSION, DIGEST, GITHUB_TOKEN)

SBOM для вложений готовит release_sbom.py."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import release_sbom
import release_summary

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "scripts" / "templates"
DIAGRAMS = {"image.svg": "схема: сборка образа", "security.svg": "схема: пайплайн безопасности", "delivery.svg": "схема: CI и релиз"}
PREVIEW_DIGEST = "sha256:" + "0" * 64
HOSTS = ("https://api.github.com/", "https://uploads.github.com/")  # других адресов github() не открывает


def package_version() -> str:
    """Версия образа: версия @cyclonedx/cdxgen в package.json."""
    return json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["dependencies"]["@cyclonedx/cdxgen"]


def changelog_section(text: str, version: str) -> str:
    """Тело раздела «## [версия]» до следующего заголовка второго уровня; пусто, если раздела нет."""
    match = re.search(rf"^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return match.group(1).strip() if match else ""


def fill(template: str, values: dict[str, str]) -> str:
    """Подставляет %%ИМЯ%% за один проход: подставленный текст повторно не раскрывается; неизвестное имя и непарные %% - ошибка."""
    def value(match: re.Match) -> str:
        if match.group(1) not in values:
            sys.exit(f"в шаблоне неизвестная подстановка %%{match.group(1)[:40]}%%")
        return values[match.group(1)]
    if template.count("%%") % 2:
        sys.exit("в шаблоне непарные %%")
    return re.sub(r"%%(.*?)%%", value, template, flags=re.S)


def components(dockerfile: str, version: str) -> str:
    """Таблица состава образа: версии и закреплённые базы берутся из ARG в Dockerfile."""
    pins = {name: (f"`{repo}:{tag}@{digest}`", repo, tag) for name, repo, tag, digest in
            re.findall(r'^ARG (\w+)_IMAGE="?(\S+?):([^:@/\s"]+)@(sha256:[0-9a-f]{64})"?[ \t]*$', dockerfile, re.M)}
    node = re.search(r"nodejs(\d+)", pins["BASE"][1]) if "BASE" in pins else None
    if not node or not {"UV", "PYTHON"} <= pins.keys():
        sys.exit("в Dockerfile не разобраны ARG BASE_IMAGE (nodejs<версия>), UV_IMAGE и PYTHON_IMAGE вида <образ>:<тег>@sha256:<digest>")
    rows = [("cdxgen", version, "npm-пакет `@cyclonedx/cdxgen`, зависимости по `package-lock.json`"),
            ("Node.js", node.group(1), pins["BASE"][0]),
            ("uv", pins["UV"][2], pins["UV"][0]),
            ("Python, только stdlib", pins["PYTHON"][2].split("-")[0], pins["PYTHON"][0])]
    return "| Компонент | Версия | Источник |\n| --- | --- | --- |\n" + "\n".join(f"| {name} | {ver} | {source} |" for name, ver, source in rows)


def values(version: str, digest: str, dockerfile: str) -> dict[str, str]:
    """Подстановки, общие для заметок релиза и описания Docker Hub."""
    if not version or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        sys.exit(f"нужны версия и digest вида sha256:<64 hex>, получено: {version!r} и {digest!r}")
    run = os.environ.get("GITHUB_RUN_ID")
    platforms = [f"`{platform}`" for platform in release_sbom.platforms(release_summary.PLATFORMS)]
    return {"VERSION": version, "TAG": f"v{version}", "DIGEST": digest, "REPOSITORY": release_summary.REPOSITORY,
            "DOCKERHUB_IMAGE": release_summary.IMAGES[0], "GHCR_IMAGE": release_summary.IMAGES[1],
            "IMAGES": release_summary.images(digest), "VERIFY": release_summary.verify(digest),
            "PLATFORMS": " и ".join(filter(None, [", ".join(platforms[:-1]), platforms[-1]])),
            "COMPONENTS": components(dockerfile, version), "RUN": f"/runs/{run}" if run else ""}


def attachments(version: str, require: bool = True) -> list[tuple[Path, str, str]]:
    """Вложения релиза (файл, тип, описание): схемы и SBOM образа по платформам; require=False - предпросмотр без файлов SBOM."""
    files = [(ROOT / "docs" / "diagrams" / name, "image/svg+xml", text) for name, text in DIAGRAMS.items()]
    boms = [(release_sbom.path(version, platform), "application/json", f"SBOM образа {platform}, SPDX")
            for platform in release_sbom.platforms(release_summary.PLATFORMS)]
    missing = [str(file) for file, _, _ in files + (boms if require else []) if not file.is_file() or not file.stat().st_size]
    if missing:
        sys.exit(f"вложения отсутствуют или пусты: {', '.join(missing)}")
    return files + boms


def notes(version: str, digest: str, changelog: str, dockerfile: str, files: list[tuple[Path, str, str]]) -> str:
    section = changelog_section(changelog, version)
    if not section:
        sys.exit(f"в CHANGELOG.md нет раздела [{version}] или он пуст")
    common = values(version, digest, dockerfile)
    download = f"https://github.com/{common['REPOSITORY']}/releases/download/{common['TAG']}"
    assets = "| Файл | Что это |\n| --- | --- |\n" + "\n".join(f"| [`{file.name}`]({download}/{file.name}) | {text} |" for file, _, text in files)
    template = (TEMPLATES / "release_notes.md").read_text(encoding="utf-8")
    return fill(template, {**common, "CHANGELOG": section, "ASSETS": assets})


def github(method: str, url: str, body: dict | bytes | None = None, content_type: str = "application/json"):
    if not url.startswith(HOSTS):
        sys.exit(f"GitHub API: адрес вне списка разрешённых: {url}")
    data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(url, method=method, data=data, headers={
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json",
        "Content-Type": content_type, "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310 — адрес проверен по HOSTS
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        detail = error.read(500).decode(errors="replace")
        error.close()
        sys.exit(f"GitHub API: {method} {url} — {error.code} {detail}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        sys.exit(f"GitHub API: {method} {url} — нет разборчивого ответа: {error}")


def find(base: str, tag: str, api) -> dict | None:
    """Release тега вместе с черновиками: GET /releases/tags/<тег> черновиков не отдаёт, поэтому перебор списка.
    Несколько Release одного тега - отказ: какой из них обновлять, решает человек."""
    found, page = [], 1
    while True:
        releases = api("GET", f"{base}?per_page=100&page={page}")
        found += [release for release in releases if release["tag_name"] == tag]
        if len(releases) < 100:
            break
        page += 1
    if len(found) > 1:
        sys.exit(f"у тега {tag} несколько Release: "
                 + ", ".join(f"{release['id']} ({'черновик' if release.get('draft') else 'опубликован'})" for release in found))
    return found[0] if found else None


def attach(base: str, release: dict, files: list[tuple[Path, str, str]], api) -> None:
    """Загружает вложения; вложение с тем же содержимым не трогается, одноимённое с другим содержимым заменяется."""
    uploaded = {asset["name"]: asset for asset in release["assets"]}
    for file, content_type, _ in files:
        data, old = file.read_bytes(), uploaded.get(file.name)
        if old and old.get("digest") == f"sha256:{hashlib.sha256(data).hexdigest()}":
            print(f"вложение {file.name}: уже загружено, {len(data)} байт")
            continue
        if old:
            api("DELETE", f"{base}/assets/{old['id']}")
        api("POST", f"{release['upload_url'].split('{')[0]}?name={urllib.parse.quote(file.name)}", data, content_type)
        print(f"вложение {file.name}: {len(data)} байт")


def publish(repository: str, tag: str, name: str, body: str, files: list[tuple[Path, str, str]], api=github) -> str:
    """Черновик, вложения, публикация: без вложений Release не виден; повторный запуск обновляет тот же Release."""
    base = f"https://api.github.com/repos/{repository}/releases"
    release = find(base, tag, api)
    if release:
        release = api("PATCH", f"{base}/{release['id']}", {"name": name, "body": body})
    else:
        release = api("POST", base, {"tag_name": tag, "name": name, "body": body, "draft": True})
    attach(base, release, files, api)
    return api("PATCH", f"{base}/{release['id']}", {"draft": False})["html_url"]


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("render", "publish"):
        sys.exit("нужна команда: render | publish")
    publishing = command == "publish"
    version = os.environ.get("VERSION") or ("" if publishing else package_version())
    digest = os.environ.get("DIGEST") or ("" if publishing else PREVIEW_DIGEST)
    files = attachments(version, require=publishing)
    body = notes(version, digest, (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"),
                 (ROOT / "Dockerfile").read_text(encoding="utf-8"), files)
    if not publishing:
        print(body, end="")
        return 0
    if os.environ.get("GITHUB_REF_TYPE") != "tag":
        sys.exit("Release создаётся только на теге")
    url = publish(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_REF_NAME"], f"cdxgen-distroless {version}", body, files)
    print(f"release: {url}, вложений: {len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
