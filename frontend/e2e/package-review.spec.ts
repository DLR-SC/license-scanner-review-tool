// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { test, expect } from '@playwright/test'
import {
  mockAll,
  makeScanResult,
  navigateToPackage,
  PACKAGE_1,
  PACKAGE_2,
  PKG1_ID,
  PKG2_ID,
  FINDING_TESTS_UNIT,
  FINDING_TESTS_INTEGRATION,
  FINDING_SOURCE,
} from './helpers.js'

test('initial load: root package list is shown', async ({ page }) => {
  await mockAll(page)
  await page.goto('/')
  await expect(page.getByRole('link', { name: PKG1_ID })).toBeVisible()
  await expect(page.getByRole('link', { name: PKG2_ID })).toBeVisible()
})

test('clicking root package navigates to its review page', async ({ page }) => {
  await mockAll(page)
  await page.goto('/')
  await page.getByRole('link', { name: PKG1_ID }).click()
  await expect(page.getByRole('cell', { name: PKG1_ID })).toBeVisible()
  await expect(page.getByText('Lodash modular utilities.')).toBeVisible()
  await expect(page.getByRole('row', { name: /Declared licenses/ })).toContainText('MIT')
  await expect(page).toHaveURL(new RegExp('/review/'))
})

test('direct URL navigation shows package info', async ({ page }) => {
  await mockAll(page)
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(page.getByRole('cell', { name: PKG1_ID })).toBeVisible()
  await expect(page.getByText('Lodash modular utilities.')).toBeVisible()
  await expect(page.getByRole('row', { name: /Declared licenses/ })).toContainText('MIT')
})

test('breadcrumb shown when navigating to a dependency', async ({ page }) => {
  // PKG2 is a dependency of PKG1 in this fixture
  await mockAll(page, {
    dependencyGraph: {
      NPM: {
        packages: [PKG1_ID, PKG2_ID],
        scopes: { 'project::test:1.0.0:dependencies': [{ root: 0 }] },
        nodes: [{ pkg: 0 }, { pkg: 1 }],
        edges: [{ from: 0, to: 1 }],
      },
    },
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await page.getByRole('link', { name: PKG2_ID }).click()
  await expect(page.getByRole('cell', { name: PKG2_ID })).toBeVisible()
  // breadcrumb should link back to PKG1
  await expect(page.getByRole('link', { name: PKG1_ID })).toBeVisible()
  expect(page.url()).toContain(PACKAGE_2.purl)
})

test('breadcrumb click navigates back to parent', async ({ page }) => {
  await mockAll(page, {
    dependencyGraph: {
      NPM: {
        packages: [PKG1_ID, PKG2_ID],
        scopes: { 'project::test:1.0.0:dependencies': [{ root: 0 }] },
        nodes: [{ pkg: 0 }, { pkg: 1 }],
        edges: [{ from: 0, to: 1 }],
      },
    },
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await page.getByRole('link', { name: PKG2_ID }).click()
  await page.getByRole('link', { name: PKG1_ID }).click()
  expect(page.url()).not.toContain(PACKAGE_2.purl)
  await expect(page.getByText('Lodash modular utilities.')).toBeVisible()
})

const graphWithDep = {
  NPM: {
    packages: [PKG1_ID, PKG2_ID],
    scopes: { 'project::test:1.0.0:dependencies': [{ root: 0 }] },
    nodes: [{ pkg: 0 }, { pkg: 1 }],
    edges: [{ from: 0, to: 1 }],
  },
}

test('clicking a dependency navigates to its review page', async ({ page }) => {
  await mockAll(page, { dependencyGraph: graphWithDep })
  await navigateToPackage(page, PACKAGE_1.purl)
  await page.getByRole('link', { name: PKG2_ID }).click()
  await expect(page.getByRole('cell', { name: PKG2_ID })).toBeVisible()
  expect(page.url()).toContain(PACKAGE_1.purl + ';' + PACKAGE_2.purl)
})

test('direct URL navigation to a nested package shows its review page', async ({ page }) => {
  await mockAll(page, { dependencyGraph: graphWithDep })
  await page.goto('/review/' + PACKAGE_1.purl + ';' + PACKAGE_2.purl)
  await expect(page.getByRole('cell', { name: PKG2_ID })).toBeVisible()
  await expect(page.getByText('Terminal string styling done right')).toBeVisible()
})

test('scoped npm dependency: clicking and direct URL navigation work correctly', async ({
  page,
}) => {
  // Scoped npm packages have PURLs containing '/' (e.g. pkg:npm/%40vue/compiler-core@3.5.25).
  // This verifies the ';' separator handles PURLs with embedded slashes without ambiguity.
  const SCOPED_ID = 'NPM:@vue:compiler-core:3.5.25'
  const SCOPED_PURL = 'pkg:npm/%40vue/compiler-core@3.5.25'
  const scopedPackage = {
    id: SCOPED_ID,
    purl: SCOPED_PURL,
    authors: [],
    declared_licenses: ['MIT'],
    declared_licenses_processed: { spdx_expression: 'MIT' },
    description: 'Vue compiler core',
    homepage_url: '',
    vcs_url: '',
    vcs_siblings: [],
  }
  const scanResult = {
    repository: { type: 'Git', url: '', revision: '', path: '' },
    projects: [],
    packages: [
      { ...scopedPackage },
      {
        id: PKG1_ID,
        purl: PACKAGE_1.purl,
        authors: [],
        declared_licenses: [],
        declared_licenses_processed: { spdx_expression: '' },
        description: '',
        homepage_url: '',
        vcs_url: '',
        vcs_siblings: [],
      },
    ],
    scan_results: [],
  }
  const dependencyGraph = {
    NPM: {
      packages: [PKG1_ID, SCOPED_ID],
      scopes: { 'project::test:1.0.0:dependencies': [{ root: 0 }] },
      nodes: [{ pkg: 0 }, { pkg: 1 }],
      edges: [{ from: 0, to: 1 }],
    },
  }
  await mockAll(page, { scanResult, dependencyGraph })

  // Direct URL navigation: PURL with '/' in it joined by ';'
  await page.goto('/review/' + PACKAGE_1.purl + ';' + SCOPED_PURL)
  await expect(page.getByRole('cell', { name: SCOPED_ID })).toBeVisible()
  await expect(page.getByText('Vue compiler core')).toBeVisible()

  // Clicking the dependency from the parent package page
  await navigateToPackage(page, PACKAGE_1.purl)
  await page.getByRole('link', { name: SCOPED_ID }).click()
  await expect(page.getByRole('cell', { name: SCOPED_ID })).toBeVisible()
  expect(page.url()).toContain(PACKAGE_1.purl + ';' + SCOPED_PURL)
})

test('detected licenses shown in metadata table, deduplicated', async ({ page }) => {
  // FINDING_TESTS_UNIT and FINDING_TESTS_INTEGRATION are both MIT → deduplicated to one entry
  // FINDING_SOURCE is Apache-2.0 → appears separately
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_SOURCE, FINDING_TESTS_INTEGRATION]),
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  const detectedRow = page.getByRole('row', { name: /Detected licenses/ })
  await expect(detectedRow).toContainText('Apache-2.0')
  await expect(detectedRow).toContainText('MIT')
})

test('path excludes fetched when navigating to a package', async ({ page }) => {
  await mockAll(page, { scanResult: makeScanResult([FINDING_TESTS_UNIT], []) })

  const [req] = await Promise.all([
    page.waitForRequest(
      (r) =>
        r.method() === 'GET' &&
        r.url().includes('/path-excludes') &&
        r.url().includes(`package_id=${encodeURIComponent(PKG2_ID)}`),
    ),
    navigateToPackage(page, PACKAGE_2.purl),
  ])
  expect(req.url()).toContain(encodeURIComponent(PKG2_ID))
})
