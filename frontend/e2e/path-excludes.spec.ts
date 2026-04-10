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

test('exclude form: open shows controls; Cancel closes with no PUT', async ({ page }) => {
  let putCalled = false
  await mockAll(page)
  await page.route('**/path-excludes**', (route) => {
    if (route.request().method() === 'PUT') putCalled = true
    return route.fulfill({ json: { package_id: PKG1_ID, path_excludes: [] } })
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await expect(page.getByRole('button', { name: 'Exclude path' })).toBeVisible()
  await page.getByRole('button', { name: 'Exclude path' }).click()
  await expect(page.getByRole('combobox').first()).toBeVisible()
  await expect(page.getByPlaceholder('Comment (optional)')).toBeVisible()

  await page.getByRole('button', { name: 'Cancel' }).click()
  await expect(page.getByRole('combobox').first()).toBeHidden()
  await page.waitForTimeout(200)
  expect(putCalled).toBe(false)
})

test('exclude form: path select contains hierarchy options', async ({ page }) => {
  // FINDING_TESTS_UNIT path = 'tests/unit/foo.ts'
  await mockAll(page)
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Exclude path' }).click()
  const select = page.getByRole('combobox').first()
  await expect(select).toBeVisible()
  await expect(select.locator('option')).toHaveText([
    'tests/**',
    'tests/unit/**',
    'tests/unit/foo.ts',
  ])
})

test('exclude form preview: −N shown and updates reactively with path selection', async ({
  page,
}) => {
  // Both findings are in tests/ — selecting tests/** should show −2
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_TESTS_INTEGRATION]),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Exclude path' }).click()
  const patternSelect = page.getByRole('combobox').first()

  await patternSelect.selectOption('tests/**')
  await expect(page.getByText('−2')).toBeVisible()

  // Narrower pattern → only FINDING_TESTS_UNIT matches → −1
  await patternSelect.selectOption('tests/unit/**')
  await expect(page.getByText('−1')).toBeVisible()
})

test('exclude form submit: PUT body correct, form closes', async ({ page }) => {
  const returnedExclude = { pattern: 'tests/**', reason: 'BUILD_TOOL_OF', comment: '' }
  // Include FINDING_MANIFEST (package.json) so a finding remains after excluding tests/**
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    onPathExcludesMutation: () => ({
      package_id: PKG1_ID,
      path_excludes: [returnedExclude],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  // FINDING_MANIFEST (package.json) sorts first (tier 0); navigate to finding 2 (tests/unit/foo.ts)
  await page.getByRole('button', { name: 'Next →' }).click()
  await page.getByRole('button', { name: 'Exclude path' }).click()
  await page.getByRole('combobox').first().selectOption('tests/**')

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === 'PUT' && r.url().includes('/path-excludes')),
    page.getByRole('button', { name: 'Confirm', exact: true }).click(),
  ])

  const body = JSON.parse(req.postData() ?? '{}')
  expect(body.package_id).toBe(PKG1_ID)
  expect(body.pattern).toBe('tests/**')
  expect(body.reason).toBe('BUILD_TOOL_OF')

  await expect(page.getByRole('combobox').first()).toBeHidden()
})

test('active exclude from GET hides matching findings', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_TESTS_INTEGRATION]),
    pathExcludes: [{ pattern: 'tests/**', reason: 'BUILD_TOOL_OF', comment: '' }],
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(page.getByText('No findings need review.')).toBeVisible()
})

test('remove path exclude: DELETE sent with correct params', async ({ page }) => {
  const existing = { pattern: 'tests/**', reason: 'BUILD_TOOL_OF', comment: '' }
  // Include FINDING_MANIFEST so a finding remains visible even with tests/** excluded
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    pathExcludes: [existing],
    onPathExcludesMutation: () => ({ package_id: PKG1_ID, path_excludes: [] }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)
  await expect(page.getByText('[tests/**]', { exact: false })).toBeVisible()

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === 'DELETE' && r.url().includes('/path-excludes')),
    page.getByRole('button', { name: '✕' }).click(),
  ])

  const url = new URL(req.url())
  expect(url.searchParams.get('package_id')).toBe(PKG1_ID)
  expect(url.searchParams.get('pattern')).toBe('tests/**')
})

test('exclude on last finding: index clamps to show remaining finding', async ({ page }) => {
  // FINDING_MANIFEST (package.json, tier 0) sorts before FINDING_TESTS_UNIT (tier 3)
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_MANIFEST]),
    onPathExcludesMutation: () => ({
      package_id: PKG1_ID,
      path_excludes: [{ pattern: 'tests/**', reason: 'BUILD_TOOL_OF', comment: '' }],
    }),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Next →' }).click()
  await expect(page.getByText('Finding 2 of 2')).toBeVisible()

  await page.getByRole('button', { name: 'Exclude path' }).click()
  await page.getByRole('combobox').first().selectOption('tests/**')
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()

  // Index clamps to 0 — FINDING_MANIFEST is the remaining finding
  await expect(page.getByText('Finding 1 of 1')).toBeVisible()
  await expect(page.getByText(FINDING_MANIFEST.location.path, { exact: false })).toBeVisible()
})

test('exclude form closes when navigating to next finding', async ({ page }) => {
  await mockAll(page, {
    scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_TESTS_INTEGRATION]),
  })
  await navigateToPackage(page, PACKAGE_1.purl)

  await page.getByRole('button', { name: 'Exclude path' }).click()
  await expect(page.getByRole('combobox').first()).toBeVisible()

  await page.getByRole('button', { name: 'Next →' }).click()
  await expect(page.getByRole('combobox').first()).toBeHidden()
})
