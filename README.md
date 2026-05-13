<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

# License Scanner Review Tool

This project is a tool for reviewing the results of a license scan performed by the [OSS Review Toolkit (ORT)](https://github.com/oss-review-toolkit/ort).

The tool consists of two main components:

- `frontend`: A web application built with Vue.js that provides a user interface for the review process.
- `server`: A FastAPI application that handles data loading and saving.

## Docker

The image bundles the FastAPI server with the prebuilt SPA. Because the frontend codegen needs the server's OpenAPI schema, build the assets first, then build the image:

```sh
# 1. Export the OpenAPI schema, generate the TS client, and build the SPA
(cd server && uv run python export_openapi.py)
(cd frontend && pnpm install --frozen-lockfile && pnpm run generate && pnpm build)

# 2. Build the image
docker build -t license-scanner-review-tool .
```

Run it against your ORT scan output:

```sh
docker run --rm -p 8000:8000 \
  -v /path/to/your/ort-out:/data/ort-out \
  -v license-scanner-cache:/cache \
  license-scanner-review-tool
```

Open <http://localhost:8000>. The container exposes two mount points:

- `/data/ort-out` — directory holding `scan-result.yml`, `package-configurations.yml`, and `curations.yml`. The server writes curations back here, so it must be writable.
- `/cache` — named volume for the external-API cache (`cache.json`), persisted across restarts.
