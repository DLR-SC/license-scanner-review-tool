<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useScanResultStore, type LicenseFinding } from '@/stores/scanResult'

const store = useScanResultStore()
onMounted(() => store.fetchScanResult())

const currentIndex = ref(0)

watch(
  () => store.packages,
  () => {
    currentIndex.value = 0
  },
)

const currentPackage = computed(() => store.packages[currentIndex.value])
const total = computed(() => store.packages.length)

const currentScanResult = computed(
  () => store.scanResults.find((sr) => sr.package_id === currentPackage.value?.id) ?? null,
)

const expandedFinding = ref<{ path: string; start_line: number } | null>(null)
const fileContent = ref<Array<{ number: number; content: string; highlighted: boolean }> | null>(
  null,
)
const fileLoading = ref(false)

async function toggleFinding(finding: LicenseFinding) {
  const isSame =
    expandedFinding.value?.path === finding.location.path &&
    expandedFinding.value?.start_line === finding.location.start_line
  if (isSame) {
    expandedFinding.value = null
    fileContent.value = null
    return
  }
  expandedFinding.value = { path: finding.location.path, start_line: finding.location.start_line }
  fileContent.value = null
  fileLoading.value = true
  try {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const params = new URLSearchParams({
      package_id: currentPackage.value!.id,
      path: finding.location.path,
      start_line: String(finding.location.start_line),
      end_line: String(finding.location.end_line),
    })
    const res = await fetch(new URL(`/file-content?${params}`, base).toString())
    if (res.ok) {
      const data = await res.json()
      fileContent.value = data.lines
    }
  } finally {
    fileLoading.value = false
  }
}

watch(currentPackage, () => {
  expandedFinding.value = null
  fileContent.value = null
})

const weeklyDownloads = ref<number | null>(null)
const downloadsLoading = ref(false)

const githubStars = ref<number | null>(null)
const starsLoading = ref(false)

watch(
  currentPackage,
  async (pkg) => {
    weeklyDownloads.value = null
    if (!pkg?.purl) return
    downloadsLoading.value = true
    try {
      const base = import.meta.env.VITE_API_BASE_URL || ''
      const res = await fetch(
        new URL(`/downloads?purl=${encodeURIComponent(pkg.purl)}`, base).toString(),
      )
      if (res.ok) {
        const data = await res.json()
        weeklyDownloads.value = data.weekly_downloads
      }
    } finally {
      downloadsLoading.value = false
    }
  },
  { immediate: true },
)

watch(
  currentPackage,
  async (pkg) => {
    githubStars.value = null
    if (!pkg?.vcs_url) return
    starsLoading.value = true
    try {
      const base = import.meta.env.VITE_API_BASE_URL || ''
      const res = await fetch(
        new URL(`/github-stars?url=${encodeURIComponent(pkg.vcs_url)}`, base).toString(),
      )
      if (res.ok) {
        const data = await res.json()
        githubStars.value = data.stars
      }
    } finally {
      starsLoading.value = false
    }
  },
  { immediate: true },
)
</script>

<template>
  <main class="p-4 gap-2 flex flex-col">
    <div v-if="store.loading">Loading…</div>
    <div v-else-if="store.error" class="text-red-500">Error: {{ store.error }}</div>

    <template v-else-if="store.packages.length">
      <div class="flex items-center justify-between mb-6">
        <h1 class="text-xl font-semibold">Package {{ currentIndex + 1 }} of {{ total }}</h1>
        <div class="flex gap-2">
          <button
            class="px-3 py-1 border rounded disabled:opacity-40"
            :disabled="currentIndex === 0"
            @click="currentIndex--"
          >
            ← Prev
          </button>
          <button
            class="px-3 py-1 border rounded disabled:opacity-40"
            :disabled="currentIndex === total - 1"
            @click="currentIndex++"
          >
            Next →
          </button>
        </div>
      </div>

      <table v-if="currentPackage" class="border-collapse w-full text-sm mb-6">
        <tbody>
          <tr>
            <th class="border px-3 py-1.5 text-left w-40">ID</th>
            <td class="border px-3 py-1.5">{{ currentPackage.id }}</td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">PURL</th>
            <td class="border px-3 py-1.5">{{ currentPackage.purl }}</td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">Description</th>
            <td class="border px-3 py-1.5">{{ currentPackage.description }}</td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">Homepage</th>
            <td class="border px-3 py-1.5">{{ currentPackage.homepage_url }}</td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">Authors</th>
            <td class="border px-3 py-1.5">{{ currentPackage.authors.join(', ') }}</td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">Declared licenses</th>
            <td class="border px-3 py-1.5">
              {{
                currentPackage.declared_licenses_processed.spdx_expression ||
                currentPackage.declared_licenses.join(', ')
              }}
            </td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left"># Dependencies</th>
            <td class="border px-3 py-1.5">{{ currentPackage.dependency_count }}</td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">Weekly downloads</th>
            <td class="border px-3 py-1.5">
              <span v-if="downloadsLoading">…</span>
              <span v-else-if="weeklyDownloads !== null">{{
                weeklyDownloads.toLocaleString()
              }}</span>
              <span v-else>—</span>
            </td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">GitHub stars</th>
            <td class="border px-3 py-1.5">
              <span v-if="starsLoading">…</span>
              <span v-else-if="githubStars !== null">{{ githubStars.toLocaleString() }}</span>
              <span v-else>—</span>
            </td>
          </tr>
        </tbody>
      </table>
      <section v-if="currentScanResult?.licenses.length" class="mt-4">
        <h2 class="text-base font-semibold mb-2">License findings</h2>
        <div
          v-for="finding in currentScanResult.licenses"
          :key="`${finding.location.path}:${finding.location.start_line}`"
          class="mb-2 border rounded"
        >
          <button
            class="w-full flex items-center gap-3 px-3 py-2 text-left text-sm hover:bg-gray-50"
            @click="toggleFinding(finding)"
          >
            <span class="font-mono font-semibold">{{ finding.license }}</span>
            <span class="text-gray-500"
              >{{ finding.location.path }}:{{ finding.location.start_line }}–{{
                finding.location.end_line
              }}</span
            >
            <span class="ml-auto text-gray-400">score {{ finding.score }}</span>
          </button>
          <template
            v-if="
              expandedFinding?.path === finding.location.path &&
              expandedFinding?.start_line === finding.location.start_line
            "
          >
            <div v-if="fileLoading" class="px-3 py-2 text-sm text-gray-400">Loading…</div>
            <div v-else-if="fileContent === null" class="px-3 py-2 text-sm text-red-400">
              Could not load file.
            </div>
            <pre
              v-else
              class="overflow-x-auto text-xs border-t"
            ><template v-for="line in fileContent" :key="line.number"><div :class="line.highlighted ? 'bg-yellow-100' : ''" class="px-3 py-px"><span class="select-none text-gray-400 mr-3 inline-block w-8 text-right">{{ line.number }}</span>{{ line.content }}</div></template></pre>
          </template>
        </div>
      </section>
    </template>
  </main>
</template>
