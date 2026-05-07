// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { test, expect } from '@playwright/test'
import { mockAll, navigateToPackage, PACKAGE_1, PKG1_ID, PKG2_ID } from './helpers.js'

const graphWithDep = {
  NPM: {
    packages: [PKG1_ID, PKG2_ID],
    scopes: { 'project::test:1.0.0:dependencies': [{ root: 0 }] },
    nodes: [{ pkg: 0 }, { pkg: 1 }],
    edges: [{ from: 0, to: 1 }],
  },
}

test.describe('GET /license-curations/all', () => {
  test('is called on initial page load', async ({ page }) => {
    const [req] = await Promise.all([
      page.waitForRequest(
        (r) => r.method() === 'GET' && r.url().includes('/license-curations/all'),
      ),
      mockAll(page).then(() => page.goto('/')),
    ])
    expect(req.url()).toContain('/license-curations/all')
  })
})

test.describe('root package list status dots', () => {
  test('package without curation shows grey dot', async ({ page }) => {
    await mockAll(page, { allLicenseCurations: [] })
    await page.goto('/')
    const button = page.locator('ul li a').filter({ hasText: PKG1_ID })
    const dot = button.locator('[aria-hidden="true"]')
    await expect(dot).toHaveClass(/text-gray-300/)
  })

  test('package with concluded license shows green dot', async ({ page }) => {
    await mockAll(page, {
      allLicenseCurations: [{ package_id: PKG1_ID, comment: '', concluded_license: 'MIT' }],
    })
    await page.goto('/')
    const button = page.locator('ul li a').filter({ hasText: PKG1_ID })
    const dot = button.locator('[aria-hidden="true"]')
    await expect(dot).toHaveClass(/text-green-500/)
  })

  test('only concluded package gets green dot, others stay grey', async ({ page }) => {
    await mockAll(page, {
      allLicenseCurations: [{ package_id: PKG1_ID, comment: '', concluded_license: 'MIT' }],
    })
    await page.goto('/')
    const btn1 = page.locator('ul li a').filter({ hasText: PKG1_ID })
    await expect(btn1.locator('[aria-hidden="true"]')).toHaveClass(/text-green-500/)

    const btn2 = page.locator('ul li a').filter({ hasText: PKG2_ID })
    await expect(btn2.locator('[aria-hidden="true"]')).toHaveClass(/text-gray-300/)
  })
})

test.describe('dependency list status dots', () => {
  test('dependency without curation shows grey dot', async ({ page }) => {
    await mockAll(page, {
      dependencyGraph: graphWithDep,
      allLicenseCurations: [],
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    const depRow = page.getByRole('row', { name: /Dependencies/ })
    const dot = depRow.locator('a').filter({ hasText: PKG2_ID }).locator('[aria-hidden="true"]')
    await expect(dot).toHaveClass(/text-gray-300/)
  })

  test('dependency with concluded license shows green dot', async ({ page }) => {
    await mockAll(page, {
      dependencyGraph: graphWithDep,
      allLicenseCurations: [{ package_id: PKG2_ID, comment: '', concluded_license: 'MIT' }],
    })
    await navigateToPackage(page, PACKAGE_1.purl)
    const depRow = page.getByRole('row', { name: /Dependencies/ })
    const dot = depRow.locator('a').filter({ hasText: PKG2_ID }).locator('[aria-hidden="true"]')
    await expect(dot).toHaveClass(/text-green-500/)
  })
})
