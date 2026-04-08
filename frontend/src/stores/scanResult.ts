// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

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
  vcs_siblings: string[]
}

export interface OrtGraphNode {
  pkg?: number
  fragment?: number
}

export interface OrtGraphEdge {
  from: number
  to: number
}

export interface OrtGraphScopeEntry {
  root: number
  fragment?: number
}

export interface OrtDependencyGraph {
  packages: string[]
  nodes: OrtGraphNode[]
  edges: OrtGraphEdge[]
  scopes: Record<string, OrtGraphScopeEntry[]>
}

export type OrtDependencyGraphs = Record<string, OrtDependencyGraph>

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

export interface LicenseFindingCuration {
  path: string
  start_lines: string
  line_count: number
  detected_license: string
  reason: string
  comment: string
  concluded_license: string
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
  const findingCurations = ref<Record<string, LicenseFindingCuration[]>>({})
  const dependencyGraph = ref<OrtDependencyGraphs | null>(null)

  const rootPackageIds = computed<string[]>(() => {
    if (!dependencyGraph.value) return []
    const ids = new Set<string>()
    for (const graph of Object.values(dependencyGraph.value)) {
      for (const scopeEntries of Object.values(graph.scopes)) {
        for (const entry of scopeEntries) {
          // entry.root is a direct index into the packages list
          const pkgId = graph.packages[entry.root]
          if (pkgId) ids.add(pkgId)
        }
      }
    }
    return [...ids]
  })

  const dependencyMap = computed<Record<string, string[]>>(() => {
    if (!dependencyGraph.value) return {}
    const map: Record<string, string[]> = {}
    for (const graph of Object.values(dependencyGraph.value)) {
      // node index → package id
      // An empty node object {} means pkg: 0 (defaults to packages[0])
      const nodeToId: Record<number, string> = {}
      for (let i = 0; i < graph.nodes.length; i++) {
        const node = graph.nodes[i]
        if (node !== undefined) {
          const pkgIdx = node.pkg ?? 0
          const pkgId = graph.packages[pkgIdx]
          if (pkgId) nodeToId[i] = pkgId
        }
      }
      // adjacency: node → child nodes
      const adj: Record<number, number[]> = {}
      for (const edge of graph.edges) {
        ;(adj[edge.from] ??= []).push(edge.to)
      }
      // build package-level dependency map
      for (const [nodeIdx, pkgId] of Object.entries(nodeToId)) {
        const childNodes = adj[Number(nodeIdx)] ?? []
        const childIds = childNodes.flatMap((n) => (nodeToId[n] ? [nodeToId[n]] : []))
        if (childIds.length > 0) {
          map[pkgId] ??= []
          for (const id of childIds) {
            if (!map[pkgId].includes(id)) map[pkgId].push(id)
          }
        }
      }
    }
    return map
  })

  async function fetchDependencyGraph() {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(new URL('/dependency-graph', base).toString())
    if (res.ok) {
      dependencyGraph.value = await res.json()
    }
  }

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
      await fetchDependencyGraph()
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

  async function fetchFindingCurations(packageId: string) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(
      new URL(`/finding-curations?package_id=${encodeURIComponent(packageId)}`, base).toString(),
    )
    if (res.ok) {
      const data: { package_id: string; license_finding_curations: LicenseFindingCuration[] } =
        await res.json()
      findingCurations.value = {
        ...findingCurations.value,
        [packageId]: data.license_finding_curations,
      }
    }
  }

  async function setFindingCuration(packageId: string, curation: LicenseFindingCuration) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(new URL('/finding-curations', base).toString(), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ package_id: packageId, ...curation }),
    })
    if (res.ok) {
      const data: { package_id: string; license_finding_curations: LicenseFindingCuration[] } =
        await res.json()
      findingCurations.value = {
        ...findingCurations.value,
        [packageId]: data.license_finding_curations,
      }
    }
  }

  async function removeFindingCuration(
    packageId: string,
    path: string,
    startLines: string,
    detectedLicense: string,
  ) {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(
      new URL(
        `/finding-curations?package_id=${encodeURIComponent(packageId)}&path=${encodeURIComponent(path)}&start_lines=${encodeURIComponent(startLines)}&detected_license=${encodeURIComponent(detectedLicense)}`,
        base,
      ).toString(),
      { method: 'DELETE' },
    )
    if (res.ok) {
      const data: { package_id: string; license_finding_curations: LicenseFindingCuration[] } =
        await res.json()
      findingCurations.value = {
        ...findingCurations.value,
        [packageId]: data.license_finding_curations,
      }
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
    findingCurations,
    dependencyGraph,
    rootPackageIds,
    dependencyMap,
    fetchScanResult,
    fetchDependencyGraph,
    fetchPathExcludes,
    addPathExclude,
    removePathExclude,
    fetchCuration,
    setCuration,
    removeCuration,
    fetchFindingCurations,
    setFindingCuration,
    removeFindingCuration,
  }
})
