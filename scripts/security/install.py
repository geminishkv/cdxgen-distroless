"""Установка сканеров по версии и sha256 из GitHub Releases в .local/security/bin.

    python3 scripts/security/install.py trivy hadolint      — поставить (или убедиться, что стоит)
    python3 scripts/security/install.py --cache-key trivy   — ключ для actions/cache: инструмент, версия, платформа

Пин — версия в common.VERSIONS и sha256 ассета в common.ASSETS; архив с другим хешем не распаковывается."""
from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import common


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as response:  # noqa: S310 — только https к github.com, адрес собран из пинов
        return response.read()


def install(name: str) -> Path:
    key = common.platform_key()
    if (name, key) not in common.ASSETS:
        common.die(f"{name}: нет пина для платформы {key} (common.ASSETS)")
    asset, expected = common.ASSETS[(name, key)]
    version = common.VERSIONS[name]
    target = common.BIN / name
    marker = common.BIN / f".{name}-{version}-{key}"
    if target.is_file() and marker.exists():
        print(f"{name} {version}: уже стоит -> {target}")
        return target
    url = f"https://github.com/{common.REPOS[name]}/releases/download/v{version}/{asset}"
    print(f"{name} {version}: {url}")
    data = download(url)
    if (digest := sha256(data)) != expected:
        common.die(f"{asset}: sha256 {digest} не совпадает с пином {expected}")
    common.BIN.mkdir(parents=True, exist_ok=True)
    if asset.endswith(".tar.gz"):
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive, tempfile.TemporaryDirectory() as tmp:
            member = next((m for m in archive.getmembers() if m.isfile() and Path(m.name).name == name), None)
            if member is None:
                common.die(f"{asset}: в архиве нет файла {name}")
            archive.extract(member, tmp, filter="data")
            shutil.move(str(Path(tmp) / member.name), target)
    else:
        target.write_bytes(data)
    target.chmod(0o755)
    for old in common.BIN.glob(f".{name}-*"):
        old.unlink()
    marker.touch()
    print(f"{name} {version} -> {target} (sha256 {expected[:12]}…)")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tools", nargs="+", choices=sorted(common.VERSIONS))
    parser.add_argument("--cache-key", action="store_true", help="только напечатать key=<ключ кэша> для первого инструмента")
    args = parser.parse_args()
    if args.cache_key:
        name = args.tools[0]
        print(f"key={name}-{common.VERSIONS[name]}-{common.platform_key()}")
        return 0
    for name in args.tools:
        install(name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
