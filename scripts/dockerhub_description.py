"""Описание репозитория на Docker Hub: текст - шаблон scripts/templates/dockerhub.md, краткое описание - метка образа в Dockerfile.

    python3 scripts/dockerhub_description.py render    - напечатать описание; без VERSION и DIGEST - предпросмотр с нулевым digest
    python3 scripts/dockerhub_description.py publish   - обновить описание (VERSION, DIGEST, DOCKERHUB_USERNAME, DOCKERHUB_DESCRIPTION_TOKEN)

Менять описание Docker Hub разрешает только токену с правами Read, Write, Delete, поэтому токен отдельный от публикации образа.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

import release_notes
import release_summary

HUB = "https://hub.docker.com/v2"
SHORT_LIMIT, FULL_LIMIT = 100, 25000  # лимиты Docker Hub в байтах: краткое и полное описание
NAMESPACE, NAME = r"[a-z0-9]+(?:[_-]+[a-z0-9]+)*", r"[a-z0-9]+(?:[._-]+[a-z0-9]+)*"  # в пространстве имён Docker Hub точек нет


def repository() -> str:
    """Пространство имён и репозиторий Docker Hub из DOCKERHUB_IMAGE."""
    match = re.fullmatch(rf"(?:docker\.io/)?({NAMESPACE}/{NAME})", release_summary.IMAGES[0])
    if not match:
        sys.exit(f"DOCKERHUB_IMAGE должен иметь вид docker.io/<пространство имён>/<репозиторий> без тега, получено: {release_summary.IMAGES[0]!r}")
    return match.group(1)


def short(dockerfile: str) -> str:
    match = re.search(r'org\.opencontainers\.image\.description="([^"\\]+)"', dockerfile)
    if not match or len(match.group(1).encode()) > SHORT_LIMIT:
        sys.exit(f"в Dockerfile нет метки org.opencontainers.image.description без экранирования и не длиннее {SHORT_LIMIT} байт")
    return match.group(1)


def overview(version: str, digest: str, dockerfile: str) -> str:
    template = (release_notes.TEMPLATES / "dockerhub.md").read_text(encoding="utf-8")
    text = release_notes.fill(template, release_notes.values(version, digest, dockerfile))
    if len(text.encode()) > FULL_LIMIT:
        sys.exit(f"описание для Docker Hub длиннее {FULL_LIMIT} байт: {len(text.encode())}")
    return text


def hub(method: str, path: str, body: dict, token: str = "") -> dict:
    request = urllib.request.Request(f"{HUB}{path}", method=method, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 — только HUB
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        detail = error.read(300).decode(errors="replace")
        error.close()
        hint = ": токену не хватает прав Read, Write, Delete либо запрос отклонил WAF Docker Hub из-за текста описания" \
            if error.code == 403 and method == "PATCH" else ""
        sys.exit(f"Docker Hub API: {method} {path} — {error.code} {detail}{hint}")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        sys.exit(f"Docker Hub API: {method} {path} — нет разборчивого ответа: {error}")


def publish(name: str, username: str, secret: str, description: str, full: str, api=hub) -> None:
    token = api("POST", "/auth/token", {"identifier": username, "secret": secret}).get("access_token")
    if not token:
        sys.exit("Docker Hub API: в ответе на вход нет access_token")
    api("PATCH", f"/repositories/{name}", {"description": description, "full_description": full}, token)


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command not in ("render", "publish"):
        sys.exit("нужна команда: render | publish")
    publishing = command == "publish"
    version = os.environ.get("VERSION") or ("" if publishing else release_notes.package_version())
    digest = os.environ.get("DIGEST") or ("" if publishing else release_notes.PREVIEW_DIGEST)
    dockerfile = (release_notes.ROOT / "Dockerfile").read_text(encoding="utf-8")
    name, description, full = repository(), short(dockerfile), overview(version, digest, dockerfile)
    if not publishing:
        print(full, end="")
        return 0
    username, secret = os.environ.get("DOCKERHUB_USERNAME"), os.environ.get("DOCKERHUB_DESCRIPTION_TOKEN")
    if not username or not secret:
        sys.exit("не заданы секреты DOCKERHUB_USERNAME и DOCKERHUB_DESCRIPTION_TOKEN (токен Docker Hub с правами Read, Write, Delete)")
    publish(name, username, secret, description, full)
    print(f"docker hub: описание {name} обновлено, {len(full.encode())} байт, краткое — {len(description.encode())} байт")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
