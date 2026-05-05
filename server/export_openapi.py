# SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
#
# SPDX-License-Identifier: Apache-2.0

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from main import app  # noqa: E402

out = Path(__file__).parent.parent / "frontend" / "openapi.json"
out.write_text(json.dumps(app.openapi(), indent=2))
print(f"Wrote {out}")
