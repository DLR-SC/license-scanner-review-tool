// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { describe, it, expect } from 'vitest'
import { spdxMatchSet } from './spdx'

describe('spdxMatchSet', () => {
  it('returns empty set for empty string', () => {
    expect(spdxMatchSet('')).toEqual(new Set())
  })

  it('returns empty set for invalid expression', () => {
    expect(spdxMatchSet('NOT A VALID EXPRESSION !!!')).toEqual(new Set())
  })

  it('returns the single license for a simple expression', () => {
    expect(spdxMatchSet('MIT')).toEqual(new Set(['MIT']))
  })

  it('returns each component for an AND expression', () => {
    expect(spdxMatchSet('MIT AND Apache-2.0')).toEqual(new Set(['MIT', 'Apache-2.0']))
  })

  it('returns all components for a chained AND expression', () => {
    expect(spdxMatchSet('MIT AND Apache-2.0 AND ISC')).toEqual(
      new Set(['MIT', 'Apache-2.0', 'ISC']),
    )
  })

  it('returns the serialized OR expression for a simple OR', () => {
    expect(spdxMatchSet('MIT OR Apache-2.0')).toEqual(new Set(['MIT OR Apache-2.0']))
  })

  it('does not include individual components of an OR expression', () => {
    const set = spdxMatchSet('MIT OR Apache-2.0')
    expect(set.has('MIT')).toBe(false)
    expect(set.has('Apache-2.0')).toBe(false)
  })

  it('splits AND at the top level but keeps nested OR as a unit', () => {
    expect(spdxMatchSet('(MIT OR ISC) AND Apache-2.0')).toEqual(
      new Set(['MIT OR ISC', 'Apache-2.0']),
    )
  })

  it('keeps a chained OR as a single serialized string', () => {
    expect(spdxMatchSet('MIT OR Apache-2.0 OR ISC')).toEqual(new Set(['MIT OR Apache-2.0 OR ISC']))
  })

  it('handles LicenseRef identifiers', () => {
    expect(spdxMatchSet('LicenseRef-scancode-public-domain')).toEqual(
      new Set(['LicenseRef-scancode-public-domain']),
    )
  })

  it('handles license exceptions', () => {
    expect(spdxMatchSet('GPL-2.0-only WITH Classpath-exception-2.0')).toEqual(
      new Set(['GPL-2.0-only WITH Classpath-exception-2.0']),
    )
  })
})
