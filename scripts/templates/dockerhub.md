# cdxgen-distroless

Образ генератора SBOM [cdxgen](https://github.com/CycloneDX/cdxgen) на distroless: SBOM проекта без сети и без установки зависимостей, без оболочки внутри и от непривилегированного пользователя.

Исходники, документация и выпуски: [github.com/%%REPOSITORY%%](https://github.com/%%REPOSITORY%%).

## Теги

| Тег | Что это |
| --- | --- |
| `%%VERSION%%`, `latest` | текущий выпуск: cdxgen %%VERSION%%, %%PLATFORMS%% |

Версия образа равна версии cdxgen внутри. Тег может быть пересобран при обновлении базовых образов, поэтому в пайплайнах стоит закреплять digest текущего выпуска:

```bash
docker pull %%DOCKERHUB_IMAGE%%@%%DIGEST%%
```

Тот же образ опубликован в GHCR: `%%GHCR_IMAGE%%`.

## Запуск

SBOM проекта с lock-файлом: каталог монтируется только на чтение, сеть контейнеру не нужна.

```bash
IMAGE=%%DOCKERHUB_IMAGE%%@%%DIGEST%%

docker create --name cdxgen-sbom --network none \
  -v "$PWD":/app:ro "$IMAGE" \
  -t js --spec-version 1.6 --no-install-deps -o /tmp/bom.json /app
docker start -a cdxgen-sbom
docker cp cdxgen-sbom:/tmp/bom.json bom.json
docker rm cdxgen-sbom
```

Для Python-проекта без lock-файла зависимости сначала разрешает `uv pip compile` из того же образа, без установки и сборки пакетов. Этот сценарий, параметры и ограничения описаны в [README](https://github.com/%%REPOSITORY%%/blob/%%TAG%%/README.md).

## Состав

%%COMPONENTS%%

Пользователь `65532:65532`. Оболочки, `apt`, `npm` и `pip` в образе нет, `LICENSE` и `NOTICE` лежат в `/licenses`.

## Проверка подписи и происхождения

Образ подписан cosign keyless, сертификат выписан на workflow `release.yml` репозитория; в GHCR дополнительно лежит аттестация происхождения GitHub.

%%VERIFY%%

Для проверки нужен cosign 3.x; `gh attestation verify` требует выполненного `gh auth login`. Образ в Docker Hub подписан так же: в `cosign verify` меняется только адрес образа.

## SBOM и аттестации

SBOM образа в формате SPDX и provenance `mode=max` хранятся в реестре аттестациями BuildKit рядом с образом:

```bash
docker buildx imagetools inspect %%DOCKERHUB_IMAGE%%@%%DIGEST%% --format '{{ json .SBOM }}'
docker buildx imagetools inspect %%DOCKERHUB_IMAGE%%@%%DIGEST%% --format '{{ json .Provenance }}'
```

Те же SBOM файлами, по одному на платформу, приложены к [выпуску %%VERSION%%](https://github.com/%%REPOSITORY%%/releases/tag/%%TAG%%).

## Проверки перед выпуском

Образ опубликован после того, как [пайплайн безопасности](https://github.com/%%REPOSITORY%%/actions%%RUN%%) прошёл целиком: gitleaks по истории git, hadolint и Trivy по Dockerfile, Trivy по образу с гейтом на `CRITICAL` и `HIGH` с доступным исправлением. Сканировалась сборка `linux/amd64` из того же Dockerfile и тех же закреплённых входов; опубликованные образы собраны заново.

## Архитектура

![Сборка образа](https://raw.githubusercontent.com/%%REPOSITORY%%/%%TAG%%/docs/diagrams/image.svg)

![Пайплайн безопасности](https://raw.githubusercontent.com/%%REPOSITORY%%/%%TAG%%/docs/diagrams/security.svg)

![CI и релиз](https://raw.githubusercontent.com/%%REPOSITORY%%/%%TAG%%/docs/diagrams/delivery.svg)

## Лицензия

[Apache-2.0](https://github.com/%%REPOSITORY%%/blob/%%TAG%%/LICENSE), сторонние компоненты перечислены в [NOTICE](https://github.com/%%REPOSITORY%%/blob/%%TAG%%/NOTICE). Как сообщить об уязвимости, описано в [SECURITY.md](https://github.com/%%REPOSITORY%%/blob/%%TAG%%/SECURITY.md).
