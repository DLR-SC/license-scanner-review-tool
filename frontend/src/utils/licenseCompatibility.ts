// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import type parse from 'spdx-expression-parse'
import { parseSpdx, licenseAtom, licenseInExpression, buildAndExpression } from './spdx'

export type CompatibilityMatrix = Record<string, Record<string, boolean | null>>

type CompatibilityResult = true | false | 'unknown'

export type CompatibilityCase =
  | { case: 'declared-license-ok'; suggestedLicense: string; comment: string }
  | {
      case: 'needs-review'
      suggestedLicense: string
      incompatibleLicenses: string[]
      unknownLicenses: string[]
    }

const SPECIAL_UNKNOWN = new Set(['NOASSERTION', 'NONE'])

export function canDistributeAs(
  found: string,
  target: string,
  matrix: CompatibilityMatrix,
): CompatibilityResult {
  if (SPECIAL_UNKNOWN.has(found) || SPECIAL_UNKNOWN.has(target)) return 'unknown'
  if (found.startsWith('LicenseRef-') || target.startsWith('LicenseRef-')) return 'unknown'
  const row = matrix[found]
  if (!row) return 'unknown'
  const val = row[target]
  if (val === true) return true
  if (val === false) return false
  return 'unknown'
}

function isCompatibleWithNode(
  found: string,
  node: parse.Info,
  matrix: CompatibilityMatrix,
): CompatibilityResult {
  if ('conjunction' in node) {
    const left = isCompatibleWithNode(found, node.left, matrix)
    const right = isCompatibleWithNode(found, node.right, matrix)
    if (node.conjunction === 'or') {
      if (left === true || right === true) return true
      if (left === false && right === false) return false
      return 'unknown'
    } else {
      if (left === false || right === false) return false
      if (left === 'unknown' || right === 'unknown') return 'unknown'
      return true
    }
  }
  return canDistributeAs(found, licenseAtom(node), matrix)
}

function isCompatibleWithExpression(
  found: string,
  declaredExpression: string,
  matrix: CompatibilityMatrix,
): CompatibilityResult {
  const parsed = parseSpdx(declaredExpression)
  if (!parsed) return 'unknown'
  return isCompatibleWithNode(found, parsed, matrix)
}

export function analyzeCompatibility(
  effectiveLicenses: string[],
  declaredExpression: string,
  matrix: CompatibilityMatrix,
): CompatibilityCase {
  const unique = [...new Set(effectiveLicenses)]

  // All effective licenses are covered by the declared expression
  if (unique.length === 0 || unique.every((id) => licenseInExpression(id, declaredExpression))) {
    return {
      case: 'declared-license-ok',
      suggestedLicense: declaredExpression,
      comment: `After reviewing all license findings, the license is concluded to be ${declaredExpression}.`,
    }
  }

  // Check compatibility of licenses not already in the declared expression
  const uncovered = unique.filter((id) => !licenseInExpression(id, declaredExpression))
  const incompatibleSet = new Set<string>()
  const unknownSet = new Set<string>()

  for (const found of uncovered) {
    const result = isCompatibleWithExpression(found, declaredExpression, matrix)
    if (result === false) incompatibleSet.add(found)
    else if (result === 'unknown') unknownSet.add(found)
  }

  if (incompatibleSet.size === 0 && unknownSet.size === 0) {
    return {
      case: 'declared-license-ok',
      suggestedLicense: declaredExpression,
      comment: `After reviewing all license findings, all found licenses are compatible with the declared license ${declaredExpression}.`,
    }
  }

  return {
    case: 'needs-review',
    suggestedLicense: incompatibleSet.size > 0 ? buildAndExpression(unique) : declaredExpression,
    incompatibleLicenses: [...incompatibleSet],
    unknownLicenses: [...unknownSet],
  }
}
