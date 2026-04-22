// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import type parse from 'spdx-expression-parse'
import { parseSpdx, licenseAtom, extractLicenseIds, licenseInExpression, buildAndExpression } from './spdx'

export type CompatibilityMatrix = Record<string, Record<string, boolean | null>>

type CompatibilityResult = true | false | 'unknown'

export type CompatibilityCase =
  | { case: 1 | 2 | 3; suggestedLicense: string; comment: string }
  | { case: 4; suggestedLicense: string; comment: string; incompatibleLicenses: string[] }
  | { case: 5; suggestedLicense: string; comment: string; unknownLicenses: string[] }

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

  if (unique.length === 0) {
    return {
      case: 1,
      suggestedLicense: declaredExpression,
      comment: `After reviewing all license findings, the license is concluded to be ${declaredExpression}.`,
    }
  }

  const declaredIds = extractLicenseIds(declaredExpression)

  // Case 1: single effective license equals the declared expression
  if (
    unique.length === 1 &&
    (unique[0] === declaredExpression || (declaredIds.length === 1 && unique[0] === declaredIds[0]))
  ) {
    return {
      case: 1,
      suggestedLicense: declaredExpression,
      comment: `After reviewing all license findings, the license is concluded to be ${declaredExpression}.`,
    }
  }

  // Case 2: all effective licenses are already present in the declared expression
  if (unique.every((id) => licenseInExpression(id, declaredExpression))) {
    return {
      case: 2,
      suggestedLicense: declaredExpression,
      comment: `After reviewing all license findings, the license is concluded to be ${declaredExpression}.`,
    }
  }

  // Cases 3-5: evaluate compatibility against the declared expression
  const incompatibleSet = new Set<string>()
  const unknownSet = new Set<string>()

  for (const found of unique) {
    const result = isCompatibleWithExpression(found, declaredExpression, matrix)
    if (result === false) incompatibleSet.add(found)
    else if (result === 'unknown') unknownSet.add(found)
  }

  if (incompatibleSet.size > 0) {
    const andExpr = buildAndExpression(unique)
    return {
      case: 4,
      suggestedLicense: andExpr,
      comment: `After reviewing all license findings, the concluded license is ${andExpr}. Note: the declared license ${declaredExpression} is not compatible with all found licenses.`,
      incompatibleLicenses: [...incompatibleSet],
    }
  }

  if (unknownSet.size > 0) {
    return {
      case: 5,
      suggestedLicense: declaredExpression,
      comment: `After reviewing all license findings, the license compatibility with ${declaredExpression} could not be fully determined. Please review manually.`,
      unknownLicenses: [...unknownSet],
    }
  }

  return {
    case: 3,
    suggestedLicense: declaredExpression,
    comment: `After reviewing all license findings, all found licenses are compatible with the declared license ${declaredExpression}.`,
  }
}
