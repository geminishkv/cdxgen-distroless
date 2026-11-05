# Changelog

Формат — Keep a Changelog, версии образа следуют версии cdxgen внутри.

## [Unreleased]

## [12.9.0] - 2026-11-05

Первый выпуск.

### Добавлено

- Образ cdxgen 12.9.0 на distroless `nodejs24-debian13`: SBOM проекта по манифестам и lock-файлам без сети и без установки
  зависимостей.
- В образе нет оболочки, `apt`, `npm` и `pip`; пользователь `65532:65532`; `LICENSE` и `NOTICE` лежат в `/licenses`.
- `uv` 0.13.6 и стандартная библиотека Python 3.12: резолв Python-проектов без lock-файла, без установки и сборки пакетов.
- Публикация в Docker Hub и GHCR для `linux/amd64` и `linux/arm64`: provenance и SBOM в аттестациях BuildKit, подпись cosign
  keyless, аттестация происхождения GitHub.
- Пайплайн безопасности перед публикацией: gitleaks, hadolint, Trivy по Dockerfile и по сборке образа с гейтом, SBOM.
- GitHub Release с SBOM опубликованных образов и схемами архитектуры во вложениях, описание репозитория на Docker Hub.

### Безопасность

- Базовые образы закреплены по digest, зависимости cdxgen ставятся по `package-lock.json` без install-скриптов.
- Override `body-parser` 2.4.0 закрывает CVE-2026-111181 (GHSA-27r3-jxmh-p828), отказ в обслуживании.
