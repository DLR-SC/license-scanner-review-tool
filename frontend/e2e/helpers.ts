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
  vcs_siblings: [],
}

// Dependency graph: both packages are root dependencies (scope entries point
// directly into the packages list by index).
export const DEPENDENCY_GRAPH = {
  NPM: {
    packages: [PKG1_ID, PKG2_ID],
    scopes: {
      'project::test:1.0.0:dependencies': [{ root: 0 }, { root: 1 }],
    },
    nodes: [],
    edges: [],
  },
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

// same file as FINDING_SOURCE — used for sibling badge tests
export const FINDING_SOURCE_SIBLING = {
  license: 'MIT',
  location: { path: 'src/main.ts', start_line: 10, end_line: 12 },
  score: 80,
}

// same file as FINDING_SOURCE, score 100 + in declared MIT → hidden (not in reviewFindings)
export const FINDING_SOURCE_HIDDEN = {
  license: 'MIT',
  location: { path: 'src/main.ts', start_line: 20, end_line: 20 },
  score: 100,
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

/** Navigate directly to the review page for a package by PURL. */
export async function navigateToPackage(page: Page, purl: string) {
  await page.goto('/review/' + purl)
}

export async function mockAll(
  page: Page,
  opts: {
    scanResult?: object
    dependencyGraph?: object
    fileContent?: object
    pathExcludes?: object[]
    onPathExcludesMutation?: (body: object) => object
    licenseCuration?: object
    onLicenseCurationsMutation?: (body: object) => object
    findingCurations?: object[]
    onFindingCurationsMutation?: (body: object) => object
  } = {},
) {
  const scanResult = opts.scanResult ?? makeScanResult([FINDING_TESTS_UNIT])
  const dependencyGraph = opts.dependencyGraph ?? DEPENDENCY_GRAPH
  const fileContent = opts.fileContent ?? FILE_CONTENT_DEFAULT
  const pathExcludes = opts.pathExcludes ?? []

  await page.route('**/scan-result', (route) => route.fulfill({ json: scanResult }))
  await page.route('**/dependency-graph', (route) => route.fulfill({ json: dependencyGraph }))
  await page.route('**/file-content**', (route) => route.fulfill({ json: fileContent }))
  await page.route('**/downloads**', (route) => route.fulfill({ json: { weekly_downloads: null } }))
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
  await page.route('**/license-curations**', (route) => {
    const method = route.request().method()
    const url = new URL(route.request().url())
    const pkgId = url.searchParams.get('package_id') ?? ''
    if (method === 'GET') {
      return route.fulfill({
        json: opts.licenseCuration ?? { package_id: pkgId, comment: '', concluded_license: null },
      })
    }
    if (method === 'PUT' && opts.onLicenseCurationsMutation) {
      const body = JSON.parse(route.request().postData() ?? '{}')
      return route.fulfill({ json: opts.onLicenseCurationsMutation(body) })
    }
    if (method === 'DELETE' && opts.onLicenseCurationsMutation) {
      return route.fulfill({ json: opts.onLicenseCurationsMutation({ package_id: pkgId }) })
    }
    return route.fulfill({ json: { package_id: pkgId, comment: '', concluded_license: null } })
  })
  const findingCurations = opts.findingCurations ?? []
  await page.route('**/finding-curations**', (route) => {
    const method = route.request().method()
    const url = new URL(route.request().url())
    const pkgId = url.searchParams.get('package_id') ?? ''
    if (method === 'GET') {
      return route.fulfill({
        json: { package_id: pkgId, license_finding_curations: findingCurations },
      })
    }
    if (method === 'PUT' && opts.onFindingCurationsMutation) {
      const body = JSON.parse(route.request().postData() ?? '{}')
      return route.fulfill({ json: opts.onFindingCurationsMutation(body) })
    }
    if (method === 'DELETE' && opts.onFindingCurationsMutation) {
      return route.fulfill({
        json: opts.onFindingCurationsMutation({
          path: url.searchParams.get('path'),
          start_lines: url.searchParams.get('start_lines'),
          detected_license: url.searchParams.get('detected_license'),
        }),
      })
    }
    return route.fulfill({
      json: { package_id: pkgId, license_finding_curations: findingCurations },
    })
  })
}
