// SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>
//
// SPDX-License-Identifier: Apache-2.0

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type {
  Repository,
  Project,
  Package,
  PackageScanResult,
  PathExclude,
  PackageCuration,
  LicenseFinding,
  LicenseFindingCuration,
  DependencyGraph,
} from '../client'
import { api } from '../api'

export type {
  Repository,
  Project,
  Package,
  PackageScanResult,
  PathExclude,
  PackageCuration,
  LicenseFinding,
  LicenseFindingCuration,
  DependencyGraph,
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
  const dependencyGraph = ref<Record<string, DependencyGraph> | null>(null)

  const rootPackageIds = computed<string[]>(() => {
    if (!dependencyGraph.value) return []
    const ids = new Set<string>()
    for (const graph of Object.values(dependencyGraph.value)) {
      for (const scopeEntries of Object.values(graph.scopes ?? {})) {
        for (const entry of scopeEntries) {
          const pkgId = (graph.packages ?? [])[entry.root]
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
      const packages = graph.packages ?? []
      const nodes = graph.nodes ?? []
      const edges = graph.edges ?? []
      const nodeToId: Record<number, string> = {}
      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i]
        if (node !== undefined) {
          const pkgIdx = node.pkg ?? 0
          const pkgId = packages[pkgIdx]
          if (pkgId) nodeToId[i] = pkgId
        }
      }
      const adj: Record<number, number[]> = {}
      for (const edge of edges) {
        ;(adj[edge.from ?? 0] ??= []).push(edge.to ?? 0)
      }
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
    const data = await api.getDependencyGraph()
    dependencyGraph.value = data
  }

  async function fetchScanResult() {
    loading.value = true
    error.value = null
    try {
      const data = await api.getScanResult()
      repository.value = data.repository
      projects.value = data.projects
      packages.value = data.packages
      scanResults.value = data.scanResults
      await fetchDependencyGraph()
      await fetchAllCurations()
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e)
    } finally {
      loading.value = false
    }
  }

  async function fetchPathExcludes(packageId: string) {
    const data = await api.getPathExcludes({ packageId })
    pathExcludes.value = { ...pathExcludes.value, [packageId]: data.pathExcludes }
  }

  async function addPathExclude(packageId: string, exclude: PathExclude) {
    const data = await api.addPathExclude({
      addPathExcludeRequest: { packageId, ...exclude },
    })
    pathExcludes.value = { ...pathExcludes.value, [packageId]: data.pathExcludes }
  }

  async function removePathExclude(packageId: string, pattern: string) {
    const data = await api.removePathExclude({ packageId, pattern })
    pathExcludes.value = { ...pathExcludes.value, [packageId]: data.pathExcludes }
  }

  async function fetchAllCurations() {
    const data = await api.getAllLicenseCurations()
    const map: Record<string, PackageCuration> = {}
    for (const c of data) {
      map[c.packageId] = c
    }
    curations.value = { ...curations.value, ...map }
  }

  async function fetchCuration(packageId: string) {
    const data = await api.getLicenseCuration({ packageId })
    curations.value = { ...curations.value, [packageId]: data }
  }

  async function setCuration(packageId: string, comment: string, concluded_license: string) {
    const data = await api.setLicenseCuration({
      setCurationRequest: { packageId, comment, concludedLicense: concluded_license },
    })
    curations.value = { ...curations.value, [packageId]: data }
  }

  async function removeCuration(packageId: string) {
    const data = await api.removeLicenseCuration({ packageId })
    curations.value = { ...curations.value, [packageId]: data }
  }

  async function fetchFindingCurations(packageId: string) {
    const data = await api.getFindingCurations({ packageId })
    findingCurations.value = {
      ...findingCurations.value,
      [packageId]: data.licenseFindingCurations,
    }
  }

  async function setFindingCuration(packageId: string, curation: LicenseFindingCuration) {
    const data = await api.setFindingCuration({
      setFindingCurationRequest: { packageId, ...curation },
    })
    findingCurations.value = {
      ...findingCurations.value,
      [packageId]: data.licenseFindingCurations,
    }
  }

  async function removeFindingCuration(
    packageId: string,
    path: string,
    startLines: string,
    detectedLicense: string,
  ) {
    const data = await api.removeFindingCuration({ packageId, path, startLines, detectedLicense })
    findingCurations.value = {
      ...findingCurations.value,
      [packageId]: data.licenseFindingCurations,
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
