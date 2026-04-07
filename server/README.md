<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

# server

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
