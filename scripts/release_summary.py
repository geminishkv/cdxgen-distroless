"""Сводка релиза для GITHUB_STEP_SUMMARY: адреса образа по digest и команды проверки подписи и аттестаций."""
import os

# Адреса, платформы и репозиторий берутся из окружения job'а (release.yml), значения по умолчанию - для локального запуска
IMAGES = (os.environ.get("DOCKERHUB_IMAGE", "docker.io/geminishkvdev/cdxgen-distroless"),
          os.environ.get("GHCR_IMAGE", "ghcr.io/geminishkv/cdxgen-distroless"))
REPOSITORY = os.environ.get("GITHUB_REPOSITORY", "geminishkv/cdxgen-distroless")
PLATFORMS = os.environ.get("PLATFORMS", "linux/amd64,linux/arm64")


def images(digest: str) -> str:
    rows = "\n".join(f"| {image.split('/')[0]} | `{image}@{digest}` |" for image in IMAGES)
    return f"| Реестр | Образ по digest |\n| --- | --- |\n{rows}"


def verify(digest: str) -> str:
    return (f"```bash\ncosign verify {IMAGES[1]}@{digest} \\\n"
            f"  --certificate-identity-regexp '^https://github.com/{REPOSITORY}/\\.github/workflows/release\\.yml@refs/' \\\n"
            "  --certificate-oidc-issuer https://token.actions.githubusercontent.com\n"
            f"gh attestation verify oci://{IMAGES[1]}@{digest} --owner {REPOSITORY.split('/')[0]}\n```")


def render(version: str, digest: str) -> str:
    return f"## Релиз cdxgen-distroless {version}\n\n{images(digest)}\n\nПроверка:\n{verify(digest)}\n"


if __name__ == "__main__":
    print(render(os.environ["VERSION"], os.environ["DIGEST"]), end="")
