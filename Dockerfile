# cdxgen на distroless: SBOM по lock-файлам без сети и резолв Python-проектов без lock-файла через uv
# без установки и сборки пакетов. Базы закреплены digest (индексы всех архитектур), зависимости cdxgen -
# по package-lock.json, в образе нет оболочки, apt, npm, pip и секретов. Сборка и проверки - README.md.
ARG BUILD_IMAGE=docker.io/library/node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0
ARG PYTHON_IMAGE=docker.io/library/python:3.12-slim@sha256:e695ab189fa2d082b1c61c69a6b888a5adeca61ceeccad107b1ed2a125721a9e
ARG BASE_IMAGE=gcr.io/distroless/nodejs24-debian13:nonroot@sha256:b8cec4b2f2126ff7bd034ec9ac207ffb3272667dfdc48376e3b035d3270549ba

FROM ${UV_IMAGE} AS uv

# Интерпретатор только для uv pip compile: stdlib без pip, ensurepip, idle, tkinter и тестов
FROM ${PYTHON_IMAGE} AS python
WORKDIR /usr/local/lib/python3.12
RUN rm -rf ensurepip idlelib tkinter turtledemo pydoc_data test config-3.12-* site-packages/*

# CVE-2026-76844: в trixie исправленного zlib ещё нет, поэтому поверх пакета базы кладётся zlib1g из Debian sid,
# запись dpkg обновляется вместе с библиотекой. Убрать стадию, когда исправление появится в базе distroless.
FROM ${PYTHON_IMAGE} AS zlib
ARG TARGETARCH
ADD --checksum=sha256:8506ce550a81ac14b047608e0df121037d9cbb10c3cc28446f68cf8c1d9d31ce \
    https://deb.debian.org/debian/pool/main/z/zlib/zlib1g_1.3.dfsg+really1.3.2-4_amd64.deb /deb/zlib1g_amd64.deb
ADD --checksum=sha256:aaf9e8cfc7d86771144c660d544806c886a5ae406f97bd50b62588a0718229ab \
    https://deb.debian.org/debian/pool/main/z/zlib/zlib1g_1.3.dfsg+really1.3.2-4_arm64.deb /deb/zlib1g_arm64.deb
RUN dpkg-deb -x "/deb/zlib1g_${TARGETARCH}.deb" /out \
    && dpkg-deb -e "/deb/zlib1g_${TARGETARCH}.deb" /ctrl \
    && install -D -m 0644 /ctrl/control /out/var/lib/dpkg/status.d/zlib1g \
    && install -m 0644 /ctrl/md5sums /out/var/lib/dpkg/status.d/zlib1g.md5sums \
    && ln -s libz.so.1.3.2 "$(dirname /out/usr/lib/*/libz.so.1)/libz.so.1.3.1"

FROM ${BUILD_IMAGE} AS build
WORKDIR /opt/cdxgen
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --omit=optional --ignore-scripts --no-audit --no-fund

# checkov:skip=CKV_DOCKER_7: базы закреплены digest в ARG по умолчанию, Checkov ARG не раскрывает
FROM ${BASE_IMAGE}
ARG CDXGEN_VERSION=unknown
ARG REVISION=unknown
ARG CREATED=unknown
COPY --from=zlib /out/ /
COPY --from=build /opt/cdxgen /opt/cdxgen
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=python /usr/local/bin/python3.12 /usr/local/bin/python3.12
COPY --from=python /usr/local/lib/libpython3.12.so.1.0 /usr/local/lib/libpython3.12.so.1.0
COPY --from=python /usr/local/lib/python3.12 /usr/local/lib/python3.12
COPY LICENSE NOTICE /licenses/
ENV HOME=/tmp
WORKDIR /app
# CIS Docker 4.1 и 4.6: явный непривилегированный uid базы nonroot; одноразовый CLI, проверка живости не нужна
USER 65532:65532
HEALTHCHECK NONE
LABEL org.opencontainers.image.title="cdxgen-distroless" \
      org.opencontainers.image.description="CycloneDX cdxgen on distroless, with uv for Python projects without a lock file" \
      org.opencontainers.image.source="https://github.com/geminishkv/cdxgen-distroless" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${CDXGEN_VERSION}" \
      org.opencontainers.image.revision="${REVISION}" \
      org.opencontainers.image.created="${CREATED}" \
      org.opencontainers.image.base.name="gcr.io/distroless/nodejs24-debian13:nonroot"
ENTRYPOINT ["/nodejs/bin/node", "/opt/cdxgen/node_modules/@cyclonedx/cdxgen/bin/cdxgen.js"]
