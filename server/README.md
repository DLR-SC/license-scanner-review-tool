<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

# server

The server is responsible for:

- CRUD operations on the ORT files
  - reading the scanner results and providing them to the frontend
  - writing the review results (curations) from the frontend back to the relevant ORT config files
- requesting additional information about the scanned dependencies from external sources (e.g. GitHub, package registries, etc.) to provide more context for the review process

## Development

### Install dependencies

```sh
uv synch
```

### Run the server

```sh
uv run fastapi dev main.py

# or use disk cache to reduce external requests
CACHE_BACKEND=disk uv run fastapi dev main.py
```

### Run tests

```sh
uv run pytest
```
