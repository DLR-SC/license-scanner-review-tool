// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { DefaultApi, Configuration } from './client'

export const api = new DefaultApi(
  new Configuration({ basePath: import.meta.env.VITE_API_BASE_URL || '' }),
)
