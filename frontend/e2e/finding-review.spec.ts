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
  FILE_CONTENT_DEFAULT,
  FINDING_TESTS_UNIT,
  FINDING_TESTS_INTEGRATION,
  FINDING_HIDDEN,
  FINDING_SOURCE,
  FINDING_SOURCE_SIBLING,
  FINDING_SOURCE_HIDDEN,
  FINDING_MANIFEST,
  FINDING_LONG,
  FINDING_SHORT,
} from './helpers.js'

test.describe('finding navigation', () => {
  test('counter advances and triggers file-content request', async ({ page }) => {
    await mockAll(page, {
      scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_TESTS_INTEGRATION]),
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('Finding 1 of 2')).toBeVisible()
    await expect(page.getByRole('button', { name: '← Prev' })).toBeDisabled()

    const [req] = await Promise.all([
      page.waitForRequest(
        (r) =>
          r.url().includes('/file-content') &&
          r.url().includes(`path=${encodeURIComponent(FINDING_TESTS_INTEGRATION.location.path)}`),
      ),
      page.getByRole('button', { name: 'Next →' }).click(),
    ])
    expect(req.url()).toContain(`start_line=${FINDING_TESTS_INTEGRATION.location.start_line}`)
    expect(req.url()).toContain(`end_line=${FINDING_TESTS_INTEGRATION.location.end_line}`)
    expect(req.url()).toContain(`package_id=${encodeURIComponent(PKG1_ID)}`)
    await expect(page.getByText('Finding 2 of 2')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Next →' })).toBeDisabled()
  })

  test('manifest file finding shown before source file finding', async ({ page }) => {
    // API returns source file first, manifest second — sort should put manifest first
    await mockAll(page, { scanResult: makeScanResult([FINDING_SOURCE, FINDING_MANIFEST]) })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('package.json', { exact: false })).toBeVisible()
    await expect(page.getByText('Finding 1 of 2')).toBeVisible()
  })

  test('score-100 in-SPDX findings excluded from counter', async ({ page }) => {
    await mockAll(page, {
      scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_HIDDEN]),
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('Finding 1 of 1')).toBeVisible()
    await expect(page.getByText(/1 finding.*hidden/)).toBeVisible()

    await page.getByRole('button', { name: 'show' }).click()
    await expect(page.getByText('src/index.ts', { exact: false })).toBeVisible()
  })
})

test.describe('context expansion', () => {
  test('expand above: button visible and increases context_before', async ({ page }) => {
    await mockAll(page, {
      fileContent: { ...FILE_CONTENT_DEFAULT, lines: FILE_CONTENT_DEFAULT.lines },
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByRole('button', { name: '↑ Load 10 more lines' })).toBeVisible()

    const [req] = await Promise.all([
      page.waitForRequest((r) => r.url().includes('/file-content')),
      page.getByRole('button', { name: '↑ Load 10 more lines' }).click(),
    ])
    expect(req.url()).toContain('context_before=15')
  })

  test('expand above: button hidden when first line is 1', async ({ page }) => {
    const contentFromLine1 = {
      lines: [
        { number: 1, content: 'line 1', highlighted: true },
        { number: 2, content: 'line 2', highlighted: false },
      ],
      total_lines: 5,
    }
    await mockAll(page, { fileContent: contentFromLine1 })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByRole('button', { name: '↑ Load 10 more lines' })).toBeHidden()
  })

  test('expand below: button visible and increases context_after', async ({ page }) => {
    await mockAll(page) // last line 10, total 100 → button should show
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByRole('button', { name: '↓ Load 10 more lines' })).toBeVisible()

    const [req] = await Promise.all([
      page.waitForRequest((r) => r.url().includes('/file-content')),
      page.getByRole('button', { name: '↓ Load 10 more lines' }).click(),
    ])
    expect(req.url()).toContain('context_after=15')
  })

  test('expand below: button hidden when last line equals total', async ({ page }) => {
    const contentAtEnd = {
      lines: [{ number: 10, content: 'last', highlighted: true }],
      total_lines: 10,
    }
    await mockAll(page, { fileContent: contentAtEnd })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByRole('button', { name: '↓ Load 10 more lines' })).toBeHidden()
  })
})

test.describe('canonical diff', () => {
  test('shown for finding spanning > 3 lines', async ({ page }) => {
    await mockAll(page, { scanResult: makeScanResult([FINDING_LONG]) })
    await page.route('**/license-text**', (route) =>
      route.fulfill({ json: { text: 'MIT License text here' } }),
    )
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText(/Diff vs. canonical/)).toBeVisible()
  })

  test('not shown for finding spanning ≤ 3 lines', async ({ page }) => {
    let licenseTextCalled = false
    await mockAll(page, { scanResult: makeScanResult([FINDING_SHORT]) })
    await page.route('**/license-text**', (route) => {
      licenseTextCalled = true
      return route.fulfill({ json: { text: '' } })
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('Finding 1 of 1')).toBeVisible()
    await page.waitForTimeout(300)
    expect(licenseTextCalled).toBe(false)
    await expect(page.getByText(/Diff vs. canonical/)).toBeHidden()
  })
})

test.describe('sibling findings', () => {
  test('no badge shown when all findings are in different files', async ({ page }) => {
    await mockAll(page, {
      scanResult: makeScanResult([FINDING_TESTS_UNIT, FINDING_TESTS_INTEGRATION]),
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('Also in file:')).toBeHidden()
  })

  test('badge shown for review sibling in same file', async ({ page }) => {
    await mockAll(page, {
      scanResult: makeScanResult([FINDING_SOURCE, FINDING_SOURCE_SIBLING]),
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('Also in file:')).toBeVisible()
    await expect(page.getByRole('button', { name: 'MIT | 80' })).toBeVisible()
  })

  test('badge click navigates to sibling finding', async ({ page }) => {
    await mockAll(page, {
      scanResult: makeScanResult([FINDING_SOURCE, FINDING_SOURCE_SIBLING]),
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('Finding 1 of 2')).toBeVisible()
    await page.getByRole('button', { name: 'MIT | 80' }).click()
    await expect(page.getByText('Finding 2 of 2')).toBeVisible()
  })

  test('after navigation badge reflects new sibling', async ({ page }) => {
    await mockAll(page, {
      scanResult: makeScanResult([FINDING_SOURCE, FINDING_SOURCE_SIBLING]),
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await page.getByRole('button', { name: 'MIT | 80' }).click()
    await expect(page.getByText('Finding 2 of 2')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Apache-2.0 | 95' })).toBeVisible()
  })

  test('hidden sibling shows disabled badge', async ({ page }) => {
    await mockAll(page, {
      scanResult: makeScanResult([FINDING_SOURCE, FINDING_SOURCE_HIDDEN]),
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    await expect(page.getByText('Also in file:')).toBeVisible()
    const badge = page.getByRole('button', { name: 'MIT | 100' })
    await expect(badge).toBeVisible()
    await expect(badge).toBeDisabled()
  })
})
