// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface VcsInfo {
  type: string
  url: string
  revision: string
  path: string
}

export interface DeclaredLicensesProcessed {
  spdx_expression: string
}

export interface Repository {
  vcs: VcsInfo
  vcs_processed: VcsInfo
}

export interface Project {
  id: string
  definition_file_path: string
  declared_licenses: string[]
  declared_licenses_processed: DeclaredLicensesProcessed
  scope_names: string[]
  homepage_url: string
  dependency_count: number
}

export interface Package {
  id: string
  purl: string
  authors: string[]
  declared_licenses: string[]
  declared_licenses_processed: DeclaredLicensesProcessed
  description: string
  homepage_url: string
  vcs_url: string
  dependency_count: number
  vcs_siblings: string[]
}

export interface LicenseLocation {
  path: string
  start_line: number
  end_line: number
}

export interface LicenseFinding {
  license: string
  location: LicenseLocation
  score: number
}

export interface PackageScanResult {
  package_id: string
  provenance: {
    vcs_info: VcsInfo
    resolved_revision: string
  }
  licenses: LicenseFinding[]
}

export interface PathExclude {
  pattern: string
  reason: string
  comment: string
}

export interface PackagePathExcludes {
  package_id: string
  path_excludes: PathExclude[]
}

export interface PackageCuration {
  package_id: string
  comment: string
  concluded_license: string | null
}

export interface OrtResult {
  repository: Repository
  projects: Project[]
  packages: Package[]
  scan_results: PackageScanResult[]
}

export const useScanResultStore = defineStore('scanResult', () => {
  const repository = ref<Repository | null>(null)
  const projects = ref<Project[]>([])
  const packages = ref<Package[]>([])
  const scanResults = ref<PackageScanResult[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)
  const pathExcludes = ref<Record<string, PathExclude[]>>({})
  const curations = ref<Record<string, PackageCuration>>({})

  async function fetchScanResult() {
    loading.value = true
    error.value = null
    try {
      const base = import.meta.env.VITE_API_BASE_URL || ''
      const res = await fetch(new URL('/scan-result', base).toString())
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `HTTP ${res.status}`)
      }
      const data: OrtResult = await res.json()
      repository.value = data.repository
      projects.value = data.projects
      packages.value = data.packages
      scanResults.value = data.scan_results
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function fetchPathExcludes(packageId: string) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(
      new URL(`/path-excludes?package_id=${encodeURIComponent(packageId)}`, base).toString(),
    )
    if (res.ok) {
      const data: PackagePathExcludes = await res.json()
      pathExcludes.value = { ...pathExcludes.value, [packageId]: data.path_excludes }
    }
  }

  async function addPathExclude(packageId: string, exclude: PathExclude) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(new URL('/path-excludes', base).toString(), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package_id: packageId, ...exclude }),
    })
    if (res.ok) {
      const data: PackagePathExcludes = await res.json()
      pathExcludes.value = { ...pathExcludes.value, [packageId]: data.path_excludes }
    }
  }

  async function removePathExclude(packageId: string, pattern: string) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(
      new URL(
        `/path-excludes?package_id=${encodeURIComponent(packageId)}&pattern=${encodeURIComponent(pattern)}`,
        base,
      ).toString(),
      { method: 'DELETE' },
    )
    if (res.ok) {
      const data: PackagePathExcludes = await res.json()
      pathExcludes.value = { ...pathExcludes.value, [packageId]: data.path_excludes }
    }
  }

  async function fetchCuration(packageId: string) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(
      new URL(`/license-curations?package_id=${encodeURIComponent(packageId)}`, base).toString(),
    )
    if (res.ok) {
      const data: PackageCuration = await res.json()
      curations.value = { ...curations.value, [packageId]: data }
    }
  }

  async function setCuration(packageId: string, comment: string, concluded_license: string) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(new URL('/license-curations', base).toString(), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package_id: packageId, comment, concluded_license }),
    })
    if (res.ok) {
      const data: PackageCuration = await res.json()
      curations.value = { ...curations.value, [packageId]: data }
    }
  }

  async function removeCuration(packageId: string) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(
      new URL(`/license-curations?package_id=${encodeURIComponent(packageId)}`, base).toString(),
      { method: 'DELETE' },
    )
    if (res.ok) {
      const data: PackageCuration = await res.json()
      curations.value = { ...curations.value, [packageId]: data }
    }
  }

  return {
    repository,
    projects,
    packages,
    scanResults,
    loading,
    error,
    pathExcludes,
    curations,
    fetchScanResult,
    fetchPathExcludes,
    addPathExclude,
    removePathExclude,
    fetchCuration,
    setCuration,
    removeCuration,
  }
})
