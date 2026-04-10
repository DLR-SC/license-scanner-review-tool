// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { test, expect } from '@playwright/test'
import {
  mockAll,
  makeScanResult,
  navigateToPackage,
  PACKAGE_1,
  PKG1_ID,
  FINDING_TESTS_UNIT,
  FINDING_TESTS_INTEGRATION,
  FINDING_MANIFEST,
} from './helpers.js'

// A pre-existing curation for FINDING_TESTS_UNIT
const CURATION_TESTS_UNIT = {
  path: FINDING_TESTS_UNIT.location.path,
  start_lines: String(FINDING_TESTS_UNIT.location.start_line),
  line_count: FINDING_TESTS_UNIT.location.end_line - FINDING_TESTS_UNIT.location.start_line + 1,
  detected_license: FINDING_TESTS_UNIT.license,
  reason: 'CODE',
  comment: '',
  concluded_license: 'MIT',
}

test('GET fetched on load with correct package_id', async ({ page }) => {
  const [req] = await Promise.all([
    page.waitForRequest(
      (r) =>
        r.method() === 'GET' &&
        r.url().includes('/finding-curations') &&
        r.url().includes(`package_id=${encodeURIComponent(PKG1_ID)}`),
    ),
    mockAll(page).then(() => navigateToPackage(page, PACKAGE_1.purl)),
  ])
  expect(req.url()).toContain(encodeURIComponent(PKG1_ID))
})

test('confirm button shows detected license in label', async ({ page }) => {
  await mockAll(page)
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(
    page.getByRole('button', { name: `Confirm as ${FINDING_TESTS_UNIT.license}` }),
  ).toBeVisible()
})

test('Other… button is visible alongside confirm button', async ({ page }) => {
  await mockAll(page)
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(page.getByRole('button', { name: 'Other…' })).toBeVisible()
})

test('one-click confirm: PUT body contains correct fields', async ({ page }) => {
  await mockAll(page, {
    onFindingCurationsMutation: (body) => ({
      package_id: PKG1_ID,
      license_finding_curations: [body],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === 'PUT' && r.url().includes('/finding-curations')),
    page.getByRole('button', { name: `Confirm as ${FINDING_TESTS_UNIT.license}` }).click(),
  ])

  const body = JSON.parse(req.postData() ?? '{}')
  expect(body.package_id).toBe(PKG1_ID)
  expect(body.path).toBe(FINDING_TESTS_UNIT.location.path)
  expect(body.start_lines).toBe(String(FINDING_TESTS_UNIT.location.start_line))
  expect(body.line_count).toBe(
    FINDING_TESTS_UNIT.location.end_line - FINDING_TESTS_UNIT.location.start_line + 1,
  )
  expect(body.detected_license).toBe(FINDING_TESTS_UNIT.license)
  expect(body.concluded_license).toBe(FINDING_TESTS_UNIT.license)
})

test('one-click confirm: finding leaves review queue', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_TESTS_INTEGRATION]),
    onFindingCurationsMutation: (body) => ({
      package_id: PKG1_ID,
      license_finding_curations: [body],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(page.getByText('Finding 1 of 2')).toBeVisible()

  await page.getByRole('button', { name: `Confirm as ${FINDING_TESTS_UNIT.license}` }).click()
  await expect(page.getByText('Finding 1 of 1')).toBeVisible()
})

test('one-click confirm on last finding: index clamps to show remaining finding', async ({
  page,
}) => {
  // FINDING_MANIFEST (package.json, tier 0) sorts before FINDING_TESTS_UNIT (tier 3)
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    onFindingCurationsMutation: (body) => ({
      package_id: PKG1_ID,
      license_finding_curations: [body],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Next →' }).click()
  await expect(page.getByText('Finding 2 of 2')).toBeVisible()

  await page.getByRole('button', { name: `Confirm as ${FINDING_TESTS_UNIT.license}` }).click()

  // Index clamps to 0 — FINDING_MANIFEST is the remaining finding
  await expect(page.getByText('Finding 1 of 1')).toBeVisible()
  await expect(page.getByText(FINDING_MANIFEST.location.path, { exact: false })).toBeVisible()
})

test('one-click confirm: reviewed summary increments', async ({ page }) => {
  await mockAll(page, {
    onFindingCurationsMutation: (body) => ({
      package_id: PKG1_ID,
      license_finding_curations: [body],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: `Confirm as ${FINDING_TESTS_UNIT.license}` }).click()
  await expect(page.getByText(/1 finding.*marked as reviewed/)).toBeVisible()
})

test('Other… form: opens with detected license pre-filled', async ({ page }) => {
  await mockAll(page)
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Other…' }).click()
  await expect(page.getByPlaceholder('SPDX expression or NONE')).toHaveValue(
    FINDING_TESTS_UNIT.license,
  )
})

test('Other… form: Cancel closes with no PUT', async ({ page }) => {
  let putCalled = false
  await mockAll(page)
  await page.route('**/finding-curations**', (route) => {
    if (route.request().method() === 'PUT') putCalled = true
    return route.fulfill({
      json: { package_id: PKG1_ID, license_finding_curations: [] },
    })
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Other…' }).click()
  await expect(page.getByPlaceholder('SPDX expression or NONE')).toBeVisible()
  await page.getByRole('button', { name: 'Cancel' }).click()

  await expect(page.getByPlaceholder('SPDX expression or NONE')).toBeHidden()
  await page.waitForTimeout(200)
  expect(putCalled).toBe(false)
})

test('Other… form: PUT body reflects edited license, reason, and comment', async ({ page }) => {
  await mockAll(page, {
    onFindingCurationsMutation: (body) => ({
      package_id: PKG1_ID,
      license_finding_curations: [body],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Other…' }).click()
  await page.getByPlaceholder('SPDX expression or NONE').fill('Apache-2.0')
  await page.getByRole('combobox').selectOption('DOCUMENTATION')
  await page.getByPlaceholder('Comment (optional)').fill('scanner matched a variable name')

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === 'PUT' && r.url().includes('/finding-curations')),
    page.getByRole('button', { name: 'Confirm' }).click(),
  ])

  const body = JSON.parse(req.postData() ?? '{}')
  expect(body.concluded_license).toBe('Apache-2.0')
  expect(body.reason).toBe('DOCUMENTATION')
  expect(body.comment).toBe('scanner matched a variable name')
})

test('Other… form: NONE can be submitted as concluded_license (no license present)', async ({
  page,
}) => {
  await mockAll(page, {
    onFindingCurationsMutation: (body) => ({
      package_id: PKG1_ID,
      license_finding_curations: [body],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Other…' }).click()
  await page.getByPlaceholder('SPDX expression or NONE').fill('NONE')

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === 'PUT' && r.url().includes('/finding-curations')),
    page.getByRole('button', { name: 'Confirm' }).click(),
  ])

  const body = JSON.parse(req.postData() ?? '{}')
  expect(body.concluded_license).toBe('NONE')
})

test('Other… form closes when navigating to next finding', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_TESTS_INTEGRATION]),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Other…' }).click()
  await expect(page.getByPlaceholder('SPDX expression or NONE')).toBeVisible()

  await page.getByRole('button', { name: 'Next →' }).click()
  await expect(page.getByPlaceholder('SPDX expression or NONE')).toBeHidden()
})

test('active curation from GET: finding excluded from review queue', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    findingCurations: [CURATION_TESTS_UNIT],
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  // Only FINDING_MANIFEST remains in the queue
  await expect(page.getByText('Finding 1 of 1')).toBeVisible()
  await expect(page.getByText('package.json', { exact: false })).toBeVisible()
})

test('active curation from GET: reviewed summary shown', async ({ page }) => {
  await mockAll(page, {
    findingCurations: [CURATION_TESTS_UNIT],
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(page.getByText(/1 finding.*marked as reviewed/)).toBeVisible()
})

test('show reviewed: concluded license displayed in list', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    findingCurations: [CURATION_TESTS_UNIT],
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'show' }).click()
  await expect(page.getByText(FINDING_TESTS_UNIT.location.path, { exact: false })).toBeVisible()
  await expect(
    page.getByText(`→ ${CURATION_TESTS_UNIT.concluded_license}`, { exact: false }),
  ).toBeVisible()
})

test('remove curation: DELETE sent with correct query params', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    findingCurations: [CURATION_TESTS_UNIT],
    onFindingCurationsMutation: () => ({
      package_id: PKG1_ID,
      license_finding_curations: [],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await page.getByRole('button', { name: 'show' }).click()

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === 'DELETE' && r.url().includes('/finding-curations')),
    page.getByRole('button', { name: '✕' }).click(),
  ])

  const url = new URL(req.url())
  expect(url.searchParams.get('package_id')).toBe(PKG1_ID)
  expect(url.searchParams.get('path')).toBe(FINDING_TESTS_UNIT.location.path)
  expect(url.searchParams.get('start_lines')).toBe(String(FINDING_TESTS_UNIT.location.start_line))
  expect(url.searchParams.get('detected_license')).toBe(FINDING_TESTS_UNIT.license)
})

test('remove curation: finding returns to review queue', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    findingCurations: [CURATION_TESTS_UNIT],
    onFindingCurationsMutation: () => ({
      package_id: PKG1_ID,
      license_finding_curations: [],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(page.getByText('Finding 1 of 1')).toBeVisible()

  await page.getByRole('button', { name: 'show' }).click()
  await page.getByRole('button', { name: '✕' }).click()

  await expect(page.getByText('Finding 1 of 2')).toBeVisible()
})
