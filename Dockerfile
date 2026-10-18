# syntax=docker/dockerfile:1
# Release = git tag v<version from pyproject.toml>, e.g. v0.1.0 (the workflow checks it).

# The dependencies are pure Python, so the virtualenv is built once on the build machine's
# own architecture and copied into every target image: no QEMU, no RUN in the final stage.
FROM --platform=$BUILDPLATFORM python:3.14.8-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app
WORKDIR /src
# dependencies first: this layer stays cached until uv.lock changes
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project
COPY pyproject.toml uv.lock LICENSE ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.14.8-slim
COPY --from=build /app /app
ENV PATH=/app/bin:$PATH PYTHONUNBUFFERED=1
# nobody: the bridge needs no files of its own, only /tmp for the health file
USER 65534:65534
# healthy = connected to both the DOMIQ Base and the broker
HEALTHCHECK --interval=30s --timeout=3s --start-period=30s \
    CMD ["python", "-c", "import os, sys; sys.exit(not os.path.exists('/tmp/domiq-mqtt.healthy'))"]
ENTRYPOINT ["domiq-mqtt"]
