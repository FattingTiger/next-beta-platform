# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579

FROM ${PYTHON_IMAGE} AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.17@sha256:03bdc89bb9798628846e60c3a9ad19006c8c3c724ccd2985a33145c039a0577b /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /opt/beta-center

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable


FROM ${PYTHON_IMAGE} AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        aapt \
        apksigner \
        ca-certificates \
        tini \
    && apt-get clean \
    && find /var/lib/apt/lists -mindepth 1 -delete \
    && groupadd --gid "${APP_GID}" --system beta-center \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" --system \
        --home-dir /nonexistent --shell /usr/sbin/nologin beta-center \
    && install --directory --owner="${APP_UID}" --group="${APP_GID}" \
        /var/lib/beta-center/storage /var/tmp/beta-center

ENV PATH="/opt/beta-center/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TMPDIR=/var/tmp/beta-center \
    BETA_STORAGE_ROOT=/var/lib/beta-center/storage \
    BETA_APKSIGNER_PATH=/usr/bin/apksigner \
    BETA_AAPT_PATH=/usr/bin/aapt
WORKDIR /opt/beta-center

COPY --from=builder --chown=${APP_UID}:${APP_GID} /opt/beta-center/.venv ./.venv
COPY --chown=${APP_UID}:${APP_GID} alembic.ini ./alembic.ini
COPY --chown=${APP_UID}:${APP_GID} alembic ./alembic
COPY --chown=${APP_UID}:${APP_GID} scripts/*.py ./scripts/
COPY --chown=${APP_UID}:${APP_GID} deploy/entrypoint.sh ./deploy/entrypoint.sh

USER ${APP_UID}:${APP_GID}
EXPOSE 8000
VOLUME ["/var/lib/beta-center/storage", "/var/tmp/beta-center"]

HEALTHCHECK --interval=20s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3).read()"]

ENTRYPOINT ["/usr/bin/tini", "--", "/opt/beta-center/deploy/entrypoint.sh"]
CMD ["uvicorn", "beta_center.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-proxy-headers", "--no-access-log"]
