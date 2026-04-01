// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import type { Page } from '@playwright/test'

// ---------------------------------------------------------------------------
// Package fixtures
// ---------------------------------------------------------------------------

export const PKG1_ID = 'NPM::lodash:4.17.21'
export const PKG2_ID = 'NPM::chalk:5.0.0'

export const PACKAGE_1 = {
  id: PKG1_ID,
  purl: 'pkg:npm/lodash@4.17.21',
  authors: ['John-David Dalton'],
  declared_licenses: ['MIT'],
  declared_licenses_processed: { spdx_expression: 'MIT' },
  description: 'Lodash modular utilities.',
  homepage_url: 'https://lodash.com',
  vcs_url: '',
  dependency_count: 0,
  vcs_siblings: [],
}

export const PACKAGE_2 = {
  id: PKG2_ID,
  purl: 'pkg:npm/chalk@5.0.0',
  authors: ['Sindre Sorhus'],
  declared_licenses: ['MIT'],
  declared_licenses_processed: { spdx_expression: 'MIT' },
  description: 'Terminal string styling done right',
  homepage_url: '',
  vcs_url: '',
  dependency_count: 0,
  vcs_siblings: [],
}

// ---------------------------------------------------------------------------
// Finding fixtures
// ---------------------------------------------------------------------------

export const FINDING_TESTS_UNIT = {
  license: 'MIT',
  location: { path: 'tests/unit/foo.ts', start_line: 1, end_line: 2 },
  score: 90,
}

export const FINDING_TESTS_INTEGRATION = {
  license: 'MIT',
  location: { path: 'tests/integration/bar.ts', start_line: 1, end_line: 2 },
  score: 85,
}

export const FINDING_HIDDEN = {
  license: 'MIT',
  location: { path: 'src/index.ts', start_line: 1, end_line: 1 },
  score: 100,
}

// source file returned first — manifest second; sort should reverse them
export const FINDING_SOURCE = {
  license: 'Apache-2.0',
  location: { path: 'src/main.ts', start_line: 1, end_line: 2 },
  score: 95,
}

export const FINDING_MANIFEST = {
  license: 'MIT',
  location: { path: 'package.json', start_line: 1, end_line: 2 },
  score: 90,
}

export const FINDING_LONG = {
  license: 'MIT',
  location: { path: 'LICENSE', start_line: 1, end_line: 30 },
  score: 80,
}

export const FINDING_SHORT = {
  license: 'MIT',
  location: { path: 'src/header.ts', start_line: 5, end_line: 7 },
  score: 80,
}

export const FILE_CONTENT_DEFAULT = {
  lines: [
    { number: 6, content: 'line 6', highlighted: false },
    { number: 7, content: 'line 7', highlighted: true },
    { number: 8, content: 'line 8', highlighted: true },
    { number: 9, content: 'line 9', highlighted: false },
    { number: 10, content: 'line 10', highlighted: false },
  ],
  total_lines: 100,
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

export function makeScanResult(pkg1Findings: object[], pkg2Findings: object[] = []) {
  return {
    repository: { type: 'Git', url: '', revision: '', path: '' },
    projects: [],
    packages: [PACKAGE_1, PACKAGE_2],
    scan_results: [
      { package_id: PKG1_ID, licenses: pkg1Findings },
      { package_id: PKG2_ID, licenses: pkg2Findings },
    ],
  }
}

export async function mockAll(
  page: Page,
  opts: {
    scanResult?: object
    fileContent?: object
    pathExcludes?: object[]
    onPathExcludesMutation?: (body: object) => object
  } = {},
) {
  const scanResult = opts.scanResult ?? makeScanResult([FINDING_TESTS_UNIT])
  const fileContent = opts.fileContent ?? FILE_CONTENT_DEFAULT
  const pathExcludes = opts.pathExcludes ?? []

  await page.route('**/scan-result', (route) => route.fulfill({ json: scanResult }))
  await page.route('**/file-content**', (route) => route.fulfill({ json: fileContent }))
  await page.route('**/downloads**', (route) =>
    route.fulfill({ json: { weekly_downloads: null } }),
  )
  await page.route('**/github-stars**', (route) => route.fulfill({ json: { stars: null } }))
  await page.route('**/path-excludes**', (route) => {
    const method = route.request().method()
    if (method === 'GET') {
      const url = new URL(route.request().url())
      const pkgId = url.searchParams.get('package_id') ?? ''
      return route.fulfill({ json: { package_id: pkgId, path_excludes: pathExcludes } })
    }
    if (method === 'PUT' && opts.onPathExcludesMutation) {
      const body = JSON.parse(route.request().postData() ?? '{}')
      return route.fulfill({ json: opts.onPathExcludesMutation(body) })
    }
    if (method === 'DELETE' && opts.onPathExcludesMutation) {
      const url = new URL(route.request().url())
      return route.fulfill({
        json: opts.onPathExcludesMutation({ pattern: url.searchParams.get('pattern') }),
      })
    }
    // default: return unchanged list
    return route.fulfill({ json: { package_id: PKG1_ID, path_excludes: pathExcludes } })
  })
}
