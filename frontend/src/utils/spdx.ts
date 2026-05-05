// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import parse from 'spdx-expression-parse'

export function serializeSpdxNode(node: parse.Info): string {
  if ('license' in node) {
    let s = node.license
    if (node.plus) s += '+'
    if (node.exception) s += ` WITH ${node.exception}`
    return s
  }
  return `${serializeSpdxNode(node.left)} ${node.conjunction.toUpperCase()} ${serializeSpdxNode(node.right)}`
}

/**
 * Builds the set of license strings a finding can match against:
 * - AND nodes are traversed — each component is added individually
 * - OR nodes are added as a whole serialized expression (e.g. "MIT OR Apache-2.0")
 */
export function spdxMatchSet(spdx: string): Set<string> {
  function collect(node: parse.Info, acc: Set<string>): void {
    if ('license' in node) {
      acc.add(serializeSpdxNode(node))
    } else if (node.conjunction === 'or') {
      acc.add(serializeSpdxNode(node))
    } else {
      collect(node.left, acc)
      collect(node.right, acc)
    }
  }
  const result = new Set<string>()
  try {
    collect(parse(spdx), result)
  } catch {
    // invalid or empty expression
  }
  return result
}
