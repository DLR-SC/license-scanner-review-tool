// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import parse from 'spdx-expression-parse'

type SpdxNode = parse.Info

export function parseSpdx(expr: string): SpdxNode | null {
  if (!expr || expr === 'NOASSERTION' || expr === 'NONE') return null
  try {
    return parse(expr)
  } catch {
    return null
  }
}

export function licenseAtom(node: parse.LicenseInfo): string {
  return node.exception ? `${node.license} WITH ${node.exception}` : node.license
}

function collectAtoms(node: SpdxNode, result: Set<string>): void {
  if ('conjunction' in node) {
    collectAtoms(node.left, result)
    collectAtoms(node.right, result)
  } else {
    result.add(licenseAtom(node))
  }
}

export function extractLicenseIds(expr: string): string[] {
  if (!expr) return []
  if (expr === 'NOASSERTION' || expr === 'NONE') return [expr]
  const parsed = parseSpdx(expr)
  if (!parsed) return [expr]
  const set = new Set<string>()
  collectAtoms(parsed, set)
  return [...set].sort()
}

function findInNode(licenseId: string, node: SpdxNode): boolean {
  if ('conjunction' in node) {
    return findInNode(licenseId, node.left) || findInNode(licenseId, node.right)
  }
  return licenseAtom(node) === licenseId
}

export function licenseInExpression(licenseId: string, expr: string): boolean {
  if (!expr) return false
  if (expr === licenseId) return true
  const parsed = parseSpdx(expr)
  if (!parsed) return expr === licenseId
  return findInNode(licenseId, parsed)
}

// Builds a canonical AND expression from a list of license atom strings.
// WITH expressions don't need extra parentheses since WITH binds tighter than AND in SPDX.
export function buildAndExpression(ids: string[]): string {
  return [...ids].sort().join(' AND ')
}
