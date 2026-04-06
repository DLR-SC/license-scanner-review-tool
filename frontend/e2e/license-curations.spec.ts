// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { test, expect } from '@playwright/test'
import { mockAll, PKG1_ID } from './helpers.js'

test('GET fetched on load with correct package_id', async ({ page }) => {
  const [req] = await Promise.all([
    page.waitForRequest(
      (r) =>
        r.method() === 'GET' &&
        r.url().includes('/license-curations') &&
        r.url().includes(`package_id=${encodeURIComponent(PKG1_ID)}`),
    ),
    mockAll(page).then(() => page.goto('/')),
  ])
  expect(req.url()).toContain(encodeURIComponent(PKG1_ID))
})

test('no curation: Trust declared license and Conclude license buttons visible', async ({
  page,
}) => {
  await mockAll(page)
  await page.goto('/')
  await expect(page.getByRole('button', { name: 'Trust declared license' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Conclude license' })).toBeVisible()
})

test('trust form: pre-fills declared SPDX expression and preset comment', async ({ page }) => {
  // PACKAGE_1 has declared_licenses_processed.spdx_expression = 'MIT'
  await mockAll(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Trust declared license' }).click()
  await expect(page.getByPlaceholder('SPDX expression')).toHaveValue('MIT')
  await expect(page.getByPlaceholder('Comment (optional)').first()).toHaveValue(
    'Declared license is correct',
  )
})

test('conclude license form opens with empty inputs', async ({ page }) => {
  await mockAll(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Conclude license' }).click()
  await expect(page.getByPlaceholder('SPDX expression')).toHaveValue('')
  await expect(page.getByPlaceholder('Comment (optional)').first()).toHaveValue('')
})

test('confirm: PUT body correct', async ({ page }) => {
  await mockAll(page, {
    onLicenseCurationsMutation: () => ({
      package_id: PKG1_ID,
      comment: 'Declared license is correct',
      concluded_license: 'MIT',
    }),
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Trust declared license' }).click()

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.method() === 'PUT' && r.url().includes('/license-curations')),
    page.getByRole('button', { name: 'Confirm' }).click(),
  ])

  const body = JSON.parse(req.postData() ?? '{}')
  expect(body.package_id).toBe(PKG1_ID)
  expect(body.concluded_license).toBe('MIT')
  expect(body.comment).toBe('Declared license is correct')
})

test('confirm: concluded license shown in row after PUT', async ({ page }) => {
  await mockAll(page, {
    onLicenseCurationsMutation: () => ({
      package_id: PKG1_ID,
      comment: 'Declared license is correct',
      concluded_license: 'MIT',
    }),
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Trust declared license' }).click()
  await page.getByRole('button', { name: 'Confirm' }).click()

  await expect(page.getByRole('row', { name: /Concluded license/ })).toContainText('MIT')
  await expect(page.getByPlaceholder('SPDX expression')).toBeHidden()
})

test('cancel: closes form with no PUT', async ({ page }) => {
  let putCalled = false
  await mockAll(page)
  await page.route('**/license-curations**', (route) => {
    if (route.request().method() === 'PUT') putCalled = true
    return route.fulfill({ json: { package_id: PKG1_ID, comment: '', concluded_license: null } })
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Trust declared license' }).click()
  await page.getByRole('button', { name: 'Cancel' }).click()

  await expect(page.getByPlaceholder('SPDX expression')).toBeHidden()
  await page.waitForTimeout(200)
  expect(putCalled).toBe(false)
})

test('active curation from GET shown on load', async ({ page }) => {
  await mockAll(page, {
    licenseCuration: {
      package_id: PKG1_ID,
      comment: 'Declared license is correct',
      concluded_license: 'MIT',
    },
  })
  await page.goto('/')
  await expect(page.getByRole('row', { name: /Concluded license/ })).toContainText('MIT')
  await expect(page.getByRole('button', { name: 'Edit' })).toBeVisible()
  await expect(page.getByRole('button', { name: '✕' })).toBeVisible()
})

test('edit pre-fills form with existing curation values', async ({ page }) => {
  await mockAll(page, {
    licenseCuration: {
      package_id: PKG1_ID,
      comment: 'my comment',
      concluded_license: 'Apache-2.0',
    },
  })
  await page.goto('/')
  await page.getByRole('button', { name: 'Edit' }).click()
  await expect(page.getByPlaceholder('SPDX expression')).toHaveValue('Apache-2.0')
  await expect(page.getByPlaceholder('Comment (optional)').first()).toHaveValue('my comment')
})

test('✕ sends DELETE with correct package_id', async ({ page }) => {
  await mockAll(page, {
    licenseCuration: { package_id: PKG1_ID, comment: '', concluded_license: 'MIT' },
    onLicenseCurationsMutation: () => ({
      package_id: PKG1_ID,
      comment: '',
      concluded_license: null,
    }),
  })
  await page.goto('/')

  const [req] = await Promise.all([
    page.waitForRequest(
      (r) => r.method() === 'DELETE' && r.url().includes('/license-curations'),
    ),
    page.getByRole('button', { name: '✕' }).click(),
  ])

  const url = new URL(req.url())
  expect(url.searchParams.get('package_id')).toBe(PKG1_ID)
})
