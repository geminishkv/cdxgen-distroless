Образ генератора SBOM [cdxgen](https://github.com/CycloneDX/cdxgen) %%VERSION%% на distroless: SBOM проекта без сети и без установки зависимостей, без оболочки внутри и от непривилегированного пользователя.

## Изменения

%%CHANGELOG%%

## Образ

%%IMAGES%%

Теги `%%VERSION%%` и `latest`, платформы %%PLATFORMS%%. Тег может быть пересобран при обновлении базовых образов, поэтому в пайплайнах стоит закреплять digest:

```bash
docker pull %%GHCR_IMAGE%%@%%DIGEST%%
docker pull %%DOCKERHUB_IMAGE%%@%%DIGEST%%
```

## Состав

%%COMPONENTS%%

Пользователь `65532:65532`. Оболочки, `apt`, `npm` и `pip` в образе нет, `LICENSE` и `NOTICE` лежат в `/licenses`.

## Запуск

SBOM проекта с lock-файлом: каталог монтируется только на чтение, сеть контейнеру не нужна.

```bash
IMAGE=%%GHCR_IMAGE%%@%%DIGEST%%

docker create --name cdxgen-sbom --network none \
  -v "$PWD":/app:ro "$IMAGE" \
  -t js --spec-version 1.6 --no-install-deps -o /tmp/bom.json /app
docker start -a cdxgen-sbom
docker cp cdxgen-sbom:/tmp/bom.json bom.json
docker rm cdxgen-sbom
```

Сценарий для Python-проекта без lock-файла, параметры и ограничения описаны в [README](https://github.com/%%REPOSITORY%%/blob/%%TAG%%/README.md).

## Проверка подписи и происхождения

%%VERIFY%%

Подпись сделана cosign 3 в формате bundle, для проверки нужен cosign 3.x; `gh attestation verify` требует выполненного `gh auth login`. Образ в Docker Hub подписан так же: в `cosign verify` меняется только адрес образа.

## SBOM и аттестации

Во вложениях лежит SBOM опубликованных образов в формате SPDX, по файлу на платформу. Это содержимое SBOM-аттестаций BuildKit, которые хранятся в реестре рядом с образом; там же provenance `mode=max`:

```bash
docker buildx imagetools inspect %%GHCR_IMAGE%%@%%DIGEST%% --format '{{ json .SBOM }}'
docker buildx imagetools inspect %%GHCR_IMAGE%%@%%DIGEST%% --format '{{ json .Provenance }}'
```

## Проверки перед выпуском

Образ опубликован после того, как пайплайн безопасности [того же прогона](https://github.com/%%REPOSITORY%%/actions%%RUN%%) прошёл целиком: gitleaks по истории git, hadolint и Trivy по Dockerfile, Trivy по образу с гейтом на `CRITICAL` и `HIGH` с доступным исправлением. Сканировалась сборка `linux/amd64` из того же Dockerfile и тех же закреплённых входов; опубликованные образы собраны заново.

## Архитектура

![Сборка образа](https://raw.githubusercontent.com/%%REPOSITORY%%/%%TAG%%/docs/diagrams/image.svg)

![Пайплайн безопасности](https://raw.githubusercontent.com/%%REPOSITORY%%/%%TAG%%/docs/diagrams/security.svg)

![CI и релиз](https://raw.githubusercontent.com/%%REPOSITORY%%/%%TAG%%/docs/diagrams/delivery.svg)

## Вложения

%%ASSETS%%
