# SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
#
# SPDX-License-Identifier: Apache-2.0

FROM python:3.12.13-slim-trixie@sha256:401f6e1a67dad31a1bd78e9ad22d0ee0a3b52154e6bd30e90be696bb6a3d7461

RUN pip install --no-cache-dir poetry==2.2.1

WORKDIR /app/server

ENV POETRY_VIRTUALENVS_IN_PROJECT=1

COPY server/pyproject.toml server/poetry.lock server/.python-version ./
RUN poetry install --no-root --without dev

COPY server/main.py ./
COPY frontend/dist /app/frontend-dist

RUN mkdir -p /data/ort-out /cache

ENV FRONTEND_DIST=/app/frontend-dist \
    ORT_OUT_PATH=/data/ort-out \
    CACHE_BACKEND=disk \
    CACHE_FILE=/cache/cache.json

EXPOSE 8000

VOLUME /data/ort-out
VOLUME /cache

CMD ["poetry", "run", "fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]
