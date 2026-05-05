<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, nextTick, useTemplateRef } from 'vue'
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { useScanResultStore } from '@/stores/scanResult'

cytoscape.use(dagre)

interface Props {
  currentPackageId: string | null
}

const props = defineProps<Props>()

const store = useScanResultStore()
const container = ref<HTMLDivElement | null>(null)
let cy: cytoscape.Core | null = null

const tooltip = ref<{ visible: boolean; text: string; x: number; y: number }>({
  visible: false,
  text: '',
  x: 0,
  y: 0,
})
const tooltipEl = useTemplateRef('tooltipEl')

function shortLabel(id: string): string {
  const parts = id.split(':')
  return parts.length >= 3 ? parts.slice(-3).join(':') : id
}

const styleSheet: cytoscape.StylesheetStyle[] = [
  {
    selector: 'node',
    style: {
      label: '',
      shape: 'ellipse',
      width: 32,
      height: 32,
      'background-color': '#9ca3af',
      'border-width': 0,
    },
  },
  {
    selector: 'node.concluded',
    style: {
      'background-color': '#22c55e',
    },
  },
  {
    selector: 'node.current',
    style: {
      'background-color': '#9ca3af',
      'border-width': 6,
      'border-color': '#1d4ed8',
      width: 40,
      height: 40,
    },
  },
  {
    selector: 'node.current.concluded',
    style: {
      'background-color': '#22c55e',
      'border-width': 6,
      'border-color': '#1d4ed8',
      width: 40,
      height: 40,
    },
  },
  {
    selector: 'node.project',
    style: {
      'background-color': '#1e293b',
      width: 40,
      height: 40,
    },
  },
  {
    selector: ':active',
    style: {
      events: 'no',
      'overlay-opacity': 0,
    },
  },
  {
    selector: 'core',
    style: {
      events: 'no',
      'active-bg-opacity': 0,
    },
  },
  {
    selector: 'edge',
    style: {
      width: 2,
      'line-color': '#9ca3af',
      'target-arrow-shape': 'triangle',
      'target-arrow-color': '#9ca3af',
      'curve-style': 'bezier',
      'arrow-scale': 1.2,
    },
  },
]

function buildElements(): cytoscape.ElementDefinition[] {
  const packageIds = new Set(store.packages.map((pkg) => pkg.id))

  const packageNodes: cytoscape.ElementDefinition[] = store.packages.map((pkg) => ({
    data: { id: pkg.id, label: shortLabel(pkg.id) },
  }))

  // Project nodes and their edges to root packages derived from scopes
  const projectNodes: cytoscape.ElementDefinition[] = []
  const projectEdges: cytoscape.ElementDefinition[] = []
  for (const [projectId, graph] of Object.entries(store.dependencyGraph ?? {})) {
    projectNodes.push({
      data: { id: projectId, label: shortLabel(projectId) },
      classes: 'project',
    })
    const rootPkgIds = new Set<string>()
    for (const scopeEntries of Object.values(graph.scopes ?? {})) {
      for (const entry of scopeEntries) {
        const pkgId = (graph.packages ?? [])[entry.root]
        if (pkgId && packageIds.has(pkgId)) rootPkgIds.add(pkgId)
      }
    }
    for (const pkgId of rootPkgIds) {
      projectEdges.push({
        data: { id: `${projectId}-->${pkgId}`, source: projectId, target: pkgId },
      })
    }
  }

  const packageEdges: cytoscape.ElementDefinition[] = Object.entries(store.dependencyMap).flatMap(
    ([from, children]) => {
      if (!packageIds.has(from)) return []
      return children
        .filter((to) => packageIds.has(to))
        .map((to) => ({
          data: { id: `${from}-->${to}`, source: from, target: to },
        }))
    },
  )

  return [...projectNodes, ...packageNodes, ...packageEdges, ...projectEdges]
}

function applyClasses() {
  if (!cy) return
  cy.nodes().forEach((node) => {
    const id = node.data('id') as string
    node.removeClass('current concluded')
    if (id === props.currentPackageId) node.addClass('current')
    if (store.curations[id]?.concludedLicense) node.addClass('concluded')
  })
}

function rebuildGraph() {
  if (!cy || store.packages.length === 0) return
  cy.resize()
  cy.elements().remove()
  cy.add(buildElements())
  const layout = cy.layout({
    name: 'dagre',
    rankDir: 'TB',
    nodeSep: 15,
    rankSep: 40,
  } as cytoscape.LayoutOptions)
  layout.one('layoutstop', () => {
    cy?.fit(cy.elements(), 16)
  })
  layout.run()
  applyClasses()
}

onMounted(async () => {
  await nextTick()
  if (!container.value) return
  cy = cytoscape({
    container: container.value,
    elements: [],
    style: styleSheet,
    userZoomingEnabled: false,
    userPanningEnabled: false,
    autoungrabify: true,
    boxSelectionEnabled: false,
  })
  cy.on('mouseover', 'node', async (e) => {
    const pos = e.target.renderedPosition() as { x: number; y: number }
    tooltip.value = {
      visible: true,
      text: e.target.data('label') as string,
      x: pos.x + 10,
      y: pos.y - 14,
    }
    // ensure tooltip does not overflow the container
    await nextTick()
    if (!tooltipEl.value || !container.value) return
    const w = tooltipEl.value.offsetWidth
    const containerW = container.value.offsetWidth
    let x = pos.x + 10
    let y = pos.y - 14
    if (x + w > containerW) x = pos.x - w - 10
    if (y < 0) y = pos.y + 14
    tooltip.value = { ...tooltip.value, x, y }
  })
  cy.on('mouseout', 'node', () => {
    tooltip.value = { ...tooltip.value, visible: false }
  })
  // Wait for the browser to finish laying out the container before
  // computing the dagre layout so cy.resize() reads real dimensions.
  requestAnimationFrame(() => {
    if (store.packages.length > 0) {
      rebuildGraph()
    }
  })
})

onUnmounted(() => {
  cy?.destroy()
  cy = null
})

watch(
  () => store.dependencyMap,
  () => {
    if (cy && store.packages.length > 0) rebuildGraph()
  },
)

watch(
  () => props.currentPackageId,
  () => {
    applyClasses()
  },
)

watch(
  () => store.curations,
  () => {
    applyClasses()
  },
  { deep: true },
)
</script>

<template>
  <div class="flex flex-col flex-1 relative" style="width: 300px">
    <div ref="container" class="w-full flex-1" />
    <div
      v-if="tooltip.visible"
      ref="tooltipEl"
      class="absolute pointer-events-none z-10 bg-white border border-gray-200 rounded px-2 py-0.5 text-sm text-gray-900 shadow-sm whitespace-nowrap"
      :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }"
    >
      {{ tooltip.text }}
    </div>
    <div
      class="absolute bottom-2 left-2 bg-white/90 border border-gray-200 rounded px-2 py-1.5 text-xs text-gray-700 shadow-sm space-y-1 pointer-events-none"
    >
      <div class="flex items-center gap-1.5">
        <span class="w-3 h-3 rounded-full bg-[#1e293b] inline-block shrink-0" />
        <span>Project</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="w-3 h-3 rounded-full bg-[#9ca3af] inline-block shrink-0" />
        <span>Package</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span class="w-3 h-3 rounded-full bg-[#22c55e] inline-block shrink-0" />
        <span>Concluded package</span>
      </div>
      <div class="flex items-center gap-1.5">
        <span
          class="w-3 h-3 rounded-full bg-transparent border-2 border-[#1d4ed8] inline-block shrink-0"
        />
        <span>Selected package</span>
      </div>
    </div>
  </div>
</template>
