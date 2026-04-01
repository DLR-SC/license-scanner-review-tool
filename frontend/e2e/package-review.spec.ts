// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { test, expect } from '@playwright/test'
import { mockAll, makeScanResult, PKG1_ID, PKG2_ID, FINDING_TESTS_UNIT } from './helpers.js'

test('initial load: package info is visible', async ({ page }) => {
  await mockAll(page)
  await page.goto('/')
  await expect(page.getByText('Package 1 of 2')).toBeVisible()
  await expect(page.getByText(PKG1_ID)).toBeVisible()
  await expect(page.getByText('Lodash modular utilities.')).toBeVisible()
  await expect(page.getByRole('row', { name: /Declared licenses/ })).toContainText('MIT')
})

test('package navigation: Prev disabled on first, Next on last', async ({ page }) => {
  await mockAll(page)
  await page.goto('/')
  await expect(page.getByText('Package 1 of 2')).toBeVisible()
  await expect(page.getByRole('button', { name: '← Prev' }).first()).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Next →' }).first()).toBeEnabled()

  await page.getByRole('button', { name: 'Next →' }).first().click()
  await expect(page.getByText('Package 2 of 2')).toBeVisible()
  await expect(page.getByRole('button', { name: '← Prev' }).first()).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Next →' }).first()).toBeDisabled()
})

test('path excludes fetched on package change', async ({ page }) => {
  await mockAll(page, { scanResult: makeScanResult([FINDING_TESTS_UNIT], []) })
  await page.goto('/')

  const [req] = await Promise.all([
    page.waitForRequest(
      (r) =>
        r.method() === 'GET' &&
        r.url().includes('/path-excludes') &&
        r.url().includes(`package_id=${encodeURIComponent(PKG2_ID)}`),
    ),
    page.getByRole('button', { name: 'Next →' }).first().click(),
  ])
  expect(req.url()).toContain(encodeURIComponent(PKG2_ID))
})
