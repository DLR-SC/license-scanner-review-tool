<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { diffWords } from 'diff'
import type { Change } from 'diff'
import { useScanResultStore, type LicenseFinding } from '@/stores/scanResult'

const store = useScanResultStore()
onMounted(() => store.fetchScanResult())

const MANIFEST_FILES = new Set([
  'pyproject.toml',
  'setup.py',
  'setup.cfg',
  'cargo.toml',
  'package.json',
  'pom.xml',
  'build.gradle',
  'composer.json',
  'go.mod',
  'go.sum',
])
const LICENSE_FILE_RE = /^(license|copying|notice|readme)/i

/**
 * Returns a sort priority tier for a license finding (lower = shown first).
 *
 * - 0: Project manifest files (e.g. pyproject.toml, package.json) — most authoritative
 * - 1: License, notice, and readme files — authoritative human-readable declarations
 * - 2: Undeclared license — license not present in the package's SPDX expression
 * - 3: Everything else
 */
function findingTier(f: LicenseFinding, spdx: string): number {
  const base = f.location.path.split('/').at(-1)?.toLowerCase() ?? ''
  if (base.endsWith('.gemspec') || MANIFEST_FILES.has(base)) return 0
  if (LICENSE_FILE_RE.test(base)) return 1
  if (!spdx.includes(f.license)) return 2
  return 3
}

const currentIndex = ref(0)

watch(
  () => store.packages,
  () => {
    currentIndex.value = 0
  },
)

const currentPackage = computed(() => store.packages[currentIndex.value])
const total = computed(() => store.packages.length)

const registryUrl = computed(() => {
  const purl = currentPackage.value?.purl
  if (!purl) return null
  if (purl.startsWith('pkg:npm/')) {
    const name = decodeURIComponent(purl.slice('pkg:npm/'.length).split('@').slice(0, -1).join('@'))
    return `https://www.npmjs.com/package/${name}`
  }
  if (purl.startsWith('pkg:pypi/')) {
    const name = purl.slice('pkg:pypi/'.length).split('@')[0]
    return `https://pypi.org/project/${name}/`
  }
  return null
})

const currentScanResult = computed(
  () => store.scanResults.find((sr) => sr.package_id === currentPackage.value?.id) ?? null,
)

const findingIndex = ref(0)

const allFindings = computed(() => currentScanResult.value?.licenses ?? [])

const reviewFindings = computed(() => {
  const spdx = currentPackage.value?.declared_licenses_processed.spdx_expression ?? ''
  return allFindings.value
    .filter((f) => f.score < 100 || !spdx.includes(f.license))
    .slice()
    .sort((a, b) => {
      const tierDiff = findingTier(a, spdx) - findingTier(b, spdx)
      return tierDiff !== 0 ? tierDiff : b.score - a.score
    })
})

const hiddenFindings = computed(() =>
  allFindings.value.filter(
    (f) =>
      f.score === 100 &&
      (currentPackage.value?.declared_licenses_processed.spdx_expression.includes(f.license) ??
        false),
  ),
)

const hiddenByLicense = computed(() => {
  const map = new Map<string, number>()
  for (const f of hiddenFindings.value) {
    map.set(f.license, (map.get(f.license) ?? 0) + 1)
  }
  return map
})

const currentFinding = computed(() => reviewFindings.value[findingIndex.value] ?? null)
const totalFindings = computed(() => reviewFindings.value.length)

const showHidden = ref(false)

const fileContent = ref<Array<{ number: number; content: string; highlighted: boolean }> | null>(
  null,
)
const fileLoading = ref(false)
const contextAbove = ref(5)
const contextBelow = ref(5)
const fileTotalLines = ref(0)

async function loadFinding(finding: LicenseFinding) {
  fileContent.value = null
  fileLoading.value = true
  try {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const params = new URLSearchParams({
      package_id: currentPackage.value!.id,
      path: finding.location.path,
      start_line: String(finding.location.start_line),
      end_line: String(finding.location.end_line),
      context_before: String(contextAbove.value),
      context_after: String(contextBelow.value),
    })
    const res = await fetch(new URL(`/file-content?${params}`, base).toString())
    if (res.ok) {
      const data = await res.json()
      fileContent.value = data.lines
      fileTotalLines.value = data.total_lines
    }
  } finally {
    fileLoading.value = false
  }
}

async function expandAbove() {
  contextAbove.value += 10
  await loadFinding(currentFinding.value!)
}

async function expandBelow() {
  contextBelow.value += 10
  await loadFinding(currentFinding.value!)
}

/**
 * Returns true when a finding likely covers a whole license text rather than
 * a single-line header — i.e. the finding spans more than 3 lines.
 */
function isWholeLicenseText(f: LicenseFinding): boolean {
  return f.location.end_line - f.location.start_line > 3
}

const canonicalText = ref<string | null>(null)
const canonicalLoading = ref(false)

async function loadCanonicalText(license: string) {
  canonicalText.value = null
  canonicalLoading.value = true
  try {
    const base = import.meta.env.VITE_API_BASE_URL || ''
    const res = await fetch(
      new URL(`/license-text?license=${encodeURIComponent(license)}`, base).toString(),
    )
    if (res.ok) {
      const data = await res.json()
      canonicalText.value = data.text
    }
  } finally {
    canonicalLoading.value = false
  }
}

const wordDiff = computed<Change[] | null>(() => {
  if (!canonicalText.value || !fileContent.value) return null
  const found = fileContent.value
    .filter((l) => l.highlighted)
    .map((l) => l.content)
    .join('\n')
  return diffWords(canonicalText.value, found)
})

watch(
  currentFinding,
  (finding) => {
    contextAbove.value = 5
    contextBelow.value = 5
    fileTotalLines.value = 0
    if (finding) {
      loadFinding(finding)
      if (isWholeLicenseText(finding)) loadCanonicalText(finding.license)
      else canonicalText.value = null
    } else {
      fileContent.value = null
      canonicalText.value = null
    }
  },
  { immediate: true },
)

watch(currentPackage, () => {
  findingIndex.value = 0
  fileContent.value = null
  canonicalText.value = null
  contextAbove.value = 5
  contextBelow.value = 5
  fileTotalLines.value = 0
  showHidden.value = false
})

const vcsSiblings = computed(() => currentPackage.value?.vcs_siblings ?? [])

function shortId(id: string): string {
  const parts = id.split(':')
  return parts.length >= 3 ? parts.slice(-3).join(':') : id
}

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
            <th class="border px-3 py-1.5 text-left">Registry</th>
            <td class="border px-3 py-1.5">
              <a
                v-if="registryUrl"
                :href="registryUrl"
                target="_blank"
                rel="noopener noreferrer"
                class="underline"
                >{{ registryUrl }}</a
              >
            </td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">Description</th>
            <td class="border px-3 py-1.5">{{ currentPackage.description }}</td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">Homepage</th>
            <td class="border px-3 py-1.5">
              <a
                v-if="currentPackage.homepage_url"
                :href="currentPackage.homepage_url"
                target="_blank"
                rel="noopener noreferrer"
                class="underline"
                >{{ currentPackage.homepage_url }}</a
              >
            </td>
          </tr>
          <tr>
            <th class="border px-3 py-1.5 text-left">VCS</th>
            <td class="border px-3 py-1.5">
              <a
                v-if="currentPackage.vcs_url"
                :href="currentPackage.vcs_url"
                target="_blank"
                rel="noopener noreferrer"
                class="underline"
                >{{ currentPackage.vcs_url }}</a
              >
            </td>
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
      <section v-if="allFindings.length" class="mt-4 flex flex-col gap-2">
        <div
          v-if="vcsSiblings.length"
          class="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2"
        >
          This package originates from the same source repository as other packages in your
          dependencies. Thus the license findings also apply to those packages:
          <span v-for="(sibling, i) in vcsSiblings" :key="sibling" class="font-mono"
            >{{ shortId(sibling) }}<span v-if="i < vcsSiblings.length - 1">, </span></span
          >.
        </div>
        <h2 class="text-base font-semibold">License findings</h2>
        <div v-if="totalFindings === 0 && allFindings.length" class="text-sm text-gray-500">
          No findings need review.
        </div>
        <template v-else-if="currentFinding">
          <div class="flex items-center justify-between mb-2">
            <h3 class="text-sm font-medium">
              Finding {{ findingIndex + 1 }} of {{ totalFindings }}
            </h3>
            <div class="flex gap-2">
              <button
                class="px-3 py-1 border rounded disabled:opacity-40"
                :disabled="findingIndex === 0"
                @click="findingIndex--"
              >
                ← Prev
              </button>
              <button
                class="px-3 py-1 border rounded disabled:opacity-40"
                :disabled="findingIndex >= totalFindings - 1"
                @click="findingIndex++"
              >
                Next →
              </button>
            </div>
          </div>
          <div class="border rounded">
            <div class="flex items-center gap-3 px-3 py-2 text-sm border-b">
              <span class="font-mono font-semibold">{{ currentFinding.license }}</span>
              <span class="text-gray-500"
                >{{ currentFinding.location.path }}:{{ currentFinding.location.start_line }}–{{
                  currentFinding.location.end_line
                }}</span
              >
              <span class="ml-auto text-gray-400">score {{ currentFinding.score }}</span>
            </div>
            <div v-if="fileLoading" class="px-3 py-2 text-sm text-gray-400">Loading…</div>
            <div v-else-if="fileContent === null" class="px-3 py-2 text-sm text-red-400">
              Could not load file.
            </div>
            <pre
              v-else
              class="overflow-x-auto text-xs"
            ><div v-if="(fileContent[0]?.number ?? 0) > 1" class="flex items-center gap-2 px-3 py-px bg-blue-50 hover:bg-blue-100 cursor-pointer select-none text-blue-600" @click="expandAbove"><span class="text-gray-400 inline-block w-8 text-right">···</span><span>↑ Load 10 more lines</span></div><template v-for="line in fileContent" :key="line.number"><div :class="line.highlighted ? 'bg-yellow-100' : ''" class="px-3 py-px"><span class="select-none text-gray-400 mr-3 inline-block w-8 text-right">{{ line.number }}</span>{{ line.content }}</div></template><div v-if="(fileContent.at(-1)?.number ?? 0) < fileTotalLines" class="flex items-center gap-2 px-3 py-px bg-blue-50 hover:bg-blue-100 cursor-pointer select-none text-blue-600" @click="expandBelow"><span class="text-gray-400 inline-block w-8 text-right">···</span><span>↓ Load 10 more lines</span></div></pre>
          </div>
          <div v-if="canonicalLoading" class="text-sm text-gray-400 mt-2">
            Loading canonical text…
          </div>
          <div v-else-if="wordDiff" class="border rounded mt-2">
            <div class="px-3 py-2 text-sm border-b text-gray-500">
              Diff vs. canonical
              <span class="font-mono">{{ currentFinding.license }}</span>
            </div>
            <pre
              class="overflow-x-auto text-xs px-3 py-2"
            ><template v-for="(change, i) in wordDiff" :key="i"><span :class="{
                'bg-green-100 text-green-800': change.added,
                'bg-red-100 text-red-700 line-through': change.removed,
              }">{{ change.value }}</span></template></pre>
          </div>
        </template>
        <div v-if="hiddenByLicense.size" class="mt-3 flex flex-col gap-1">
          <div
            v-for="[license, count] in hiddenByLicense"
            :key="license"
            class="text-sm text-gray-400"
          >
            {{ count }} finding{{ count === 1 ? '' : 's' }} of
            <span class="font-mono">{{ license }}</span> with score 100 hidden
            <button
              v-if="!showHidden"
              class="ml-1 underline text-gray-500"
              @click="showHidden = true"
            >
              show
            </button>
          </div>
          <div v-if="showHidden">
            <button class="text-sm underline text-gray-500 mb-1" @click="showHidden = false">
              hide
            </button>
            <div
              v-for="f in hiddenFindings"
              :key="`${f.location.path}:${f.location.start_line}`"
              class="text-xs font-mono text-gray-500 px-1"
            >
              <span class="font-semibold">{{ f.license }}</span>
              {{ f.location.path }}:{{ f.location.start_line }}–{{ f.location.end_line }}
              <span class="text-gray-400">score {{ f.score }}</span>
            </div>
          </div>
        </div>
      </section>
    </template>
  </main>
</template>
