<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import DescribedSelect from '@/components/DescribedSelect.vue'
import { useRoute, useRouter } from 'vue-router'
import { diffWords } from 'diff'
import type { Change } from 'diff'
import { minimatch } from 'minimatch'
import {
  useScanResultStore,
  type LicenseFinding,
  type LicenseFindingCuration,
  type Package,
} from '@/stores/scanResult'
import type { Option } from '@/components/DescribedSelect.vue'

const store = useScanResultStore()
const route = useRoute()
const router = useRouter()
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
 * https://github.com/oss-review-toolkit/ort/blob/82.0.0/model/src/main/kotlin/config/PathExcludeReason.kt
 */
const PATH_EXCLUDE_REASONS: Option[] = [
  {
    label: 'BUILD_TOOL_OF',
    description:
      'The path only contains tools used for building source code which are not included in distributed build artifacts.',
  },
  {
    label: 'DATA_FILE_OF',
    description:
      'The path only contains data files such as fonts or images which are not included in distributed build artifacts.',
  },
  {
    label: 'DOCUMENTATION_OF',
    description:
      'The path only contains documentation which is not included in distributed build artifacts.',
  },
  {
    label: 'EXAMPLE_OF',
    description:
      'The path only contains source code examples which are not included in distributed build artifacts.',
  },
  {
    label: 'OPTIONAL_COMPONENT_OF',
    description:
      'The path only contains optional components for the code that is built which are not included in distributed build artifacts.',
  },
  {
    label: 'OTHER',
    description:
      'A fallback reason for the PathExcludeReason when none of the other reasons apply.',
  },
  {
    label: 'PROVIDED_BY',
    description:
      'The path only contains packages or sources for packages that have to be provided by the user of distributed build artifacts.',
  },
  {
    label: 'TEST_OF',
    description:
      'The path only contains files used for testing source code which are not included in distributed build artifacts.',
  },
  {
    label: 'TEST_TOOL_OF',
    description:
      'The path only contains tools used for testing source code which are not included in distributed build artifacts.',
  },
]

/**
 * https://github.com/oss-review-toolkit/ort/blob/82.0.0/model/src/main/kotlin/config/LicenseFindingCurationReason.kt
 */
const LICENSE_FINDING_CURATIONS_REASONS: Option[] = [
  {
    label: 'CODE',
    description: 'The findings occur in source code, for example the name of a variable.',
  },
  {
    label: 'DATA_OF',
    description:
      'The findings occur in data, for example a JSON object defining all SPDX licenses.',
  },
  {
    label: 'DOCUMENTATION_OF',
    description:
      'The findings occur in documentation, for example in code comments or in the README.md.',
  },
  {
    label: 'INCORRECT',
    description:
      'The detected licenses are not correct. Use only if none of the other reasons apply.',
  },
  {
    label: 'NOT_DETECTED',
    description: 'Add applicable license as the scanner did not detect it.',
  },
  {
    label: 'REFERENCE',
    description:
      'The findings reference a file or URL, e.g. SEE LICENSE IN LICENSE or https://jquery.org/license/.',
  },
]

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

function pathExcludeOptions(filePath: string): string[] {
  const parts = filePath.split('/')
  const options: string[] = []
  for (let i = 1; i < parts.length; i++) {
    options.push(parts.slice(0, i).join('/') + '/**')
  }
  options.push(filePath)
  return options
}

// Navigation path: array of PURLs from the URL.
// PURLs are joined with ';' as separator (PURLs never contain ';').
// Vue Router decodes path params (e.g. %40 → @), so navigationPath entries
// are already decoded. Stored PURLs from ORT may use %40 for scoped npm
// packages, so comparisons always decode both sides.
const navigationPath = computed<string[]>(() => {
  const raw = (route.params.path as string) ?? ''
  if (!raw) return []
  return raw.split(';').filter(Boolean)
})

const currentPackage = computed(() => {
  const purl = navigationPath.value.at(-1)
  if (!purl) return null
  const decoded = decodeURIComponent(purl)
  return store.packages.find((p) => decodeURIComponent(p.purl) === decoded) ?? null
})

const purlToPackage = computed(() => {
  // Key by decoded PURL so lookups work regardless of %40 vs @ encoding.
  const map = new Map<string, Package>()
  for (const p of store.packages) map.set(decodeURIComponent(p.purl), p)
  return map
})

function purlPath(purls: string[]): string {
  return '/review/' + purls.join(';')
}

function navigateToDep(depId: string) {
  const pkg = store.packages.find((p) => p.id === depId)
  if (!pkg?.purl) return
  const newPath = [...navigationPath.value, pkg.purl]
  router.push(purlPath(newPath))
}

function navigateToRoot(purl: string) {
  router.push(purlPath([purl]))
}

// Dependencies of the current package (as package objects)
const currentDeps = computed<Package[]>(() => {
  if (!currentPackage.value) return []
  const depIds = store.dependencyMap[currentPackage.value.id] ?? []
  return depIds
    .map((id) => store.packages.find((p) => p.id === id))
    .filter((p): p is Package => !!p)
})

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

const currentExcludes = computed(() => store.pathExcludes[currentPackage.value?.id ?? ''] ?? [])

const reviewFindings = computed(() => {
  const spdx = currentPackage.value?.declared_licenses_processed.spdx_expression ?? ''
  const excludePatterns = currentExcludes.value.map((e) => e.pattern)
  const curationsMap = currentFindingCurationsMap.value
  return allFindings.value
    .filter(
      (f) =>
        (f.score < 100 || !spdx.includes(f.license)) &&
        !excludePatterns.some((p) => minimatch(f.location.path, p)) &&
        !curationsMap.has(findingCurationKey(f)),
    )
    .slice()
    .sort((a, b) => {
      const tierDiff = findingTier(a, spdx) - findingTier(b, spdx)
      return tierDiff !== 0 ? tierDiff : b.score - a.score
    })
})

const reviewedFindings = computed(() =>
  allFindings.value.filter((f) => currentFindingCurationsMap.value.has(findingCurationKey(f))),
)

function previewExcludeCount(pattern: string): number {
  return reviewFindings.value.filter((f) => minimatch(f.location.path, pattern)).length
}

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

const siblingFindingsInFile = computed(() => {
  if (!currentFinding.value) return []
  const path = currentFinding.value.location.path
  return allFindings.value.filter(
    (f) =>
      f.location.path === path &&
      !(
        f.location.start_line === currentFinding.value!.location.start_line &&
        f.location.end_line === currentFinding.value!.location.end_line &&
        f.license === currentFinding.value!.license
      ),
  )
})

const showHidden = ref(false)

const showExcludeForm = ref(false)
const excludeFormPattern = ref('')
const excludeFormReason = ref<Option['label']>('BUILD_TOOL_OF')
const excludeFormComment = ref('')

const showCurationForm = ref(false)
const curationComment = ref('')
const curationLicense = ref('')

const currentCuration = computed(() => store.curations[currentPackage.value?.id ?? ''] ?? null)

function findingCurationKey(f: LicenseFinding): string {
  return `${f.location.path}:${f.location.start_line}:${f.license}`
}

const currentFindingCurations = computed(
  () => store.findingCurations[currentPackage.value?.id ?? ''] ?? [],
)

const currentFindingCurationsMap = computed(() => {
  const map = new Map<string, LicenseFindingCuration>()
  for (const c of currentFindingCurations.value) {
    map.set(`${c.path}:${c.start_lines}:${c.detected_license}`, c)
  }
  return map
})

const showDecisionForm = ref(false)
const decisionLicense = ref('')
const decisionComment = ref('')
const decisionReason = ref<Option['label']>('CODE')

const showReviewed = ref(false)

function openTrustForm() {
  curationLicense.value = currentPackage.value?.declared_licenses_processed.spdx_expression ?? ''
  curationComment.value = 'Declared license is correct'
  showCurationForm.value = true
}

function openCurationForm() {
  curationLicense.value = currentCuration.value?.concluded_license ?? ''
  curationComment.value = currentCuration.value?.comment ?? ''
  showCurationForm.value = true
}

async function confirmCuration() {
  if (!currentPackage.value) return
  await store.setCuration(currentPackage.value.id, curationComment.value, curationLicense.value)
  showCurationForm.value = false
}

function openExcludeForm() {
  const path = currentFinding.value?.location.path ?? ''
  excludeFormPattern.value = pathExcludeOptions(path)[0] ?? path
  excludeFormReason.value = 'BUILD_TOOL_OF'
  excludeFormComment.value = ''
  showExcludeForm.value = true
}

async function confirmExclude() {
  if (!currentPackage.value) return
  await store.addPathExclude(currentPackage.value.id, {
    pattern: excludeFormPattern.value,
    reason: excludeFormReason.value,
    comment: excludeFormComment.value,
  })
  showExcludeForm.value = false
}

async function confirmFinding(f: LicenseFinding, concludedLicense: string) {
  if (!currentPackage.value) return
  await store.setFindingCuration(currentPackage.value.id, {
    path: f.location.path,
    start_lines: String(f.location.start_line),
    line_count: f.location.end_line - f.location.start_line + 1,
    detected_license: f.license,
    reason: 'CODE',
    comment: '',
    concluded_license: concludedLicense,
  })
}

async function confirmDecisionForm() {
  if (!currentPackage.value || !currentFinding.value) return
  await store.setFindingCuration(currentPackage.value.id, {
    path: currentFinding.value.location.path,
    start_lines: String(currentFinding.value.location.start_line),
    line_count:
      currentFinding.value.location.end_line - currentFinding.value.location.start_line + 1,
    detected_license: currentFinding.value.license,
    reason: decisionReason.value,
    comment: decisionComment.value,
    concluded_license: decisionLicense.value,
  })
  showDecisionForm.value = false
}

function openDecisionForm() {
  if (!currentFinding.value) return
  decisionLicense.value = currentFinding.value.license
  decisionComment.value = ''
  decisionReason.value = 'CODE'
  showDecisionForm.value = true
}

async function removeFindingCuration(f: LicenseFinding) {
  if (!currentPackage.value) return
  await store.removeFindingCuration(
    currentPackage.value.id,
    f.location.path,
    String(f.location.start_line),
    f.license,
  )
}

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
    showExcludeForm.value = false
    showDecisionForm.value = false
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

watch(reviewFindings, (findings) => {
  if (findingIndex.value >= findings.length) {
    findingIndex.value = Math.max(0, findings.length - 1)
  }
})

watch(currentPackage, (pkg) => {
  findingIndex.value = 0
  fileContent.value = null
  canonicalText.value = null
  contextAbove.value = 5
  contextBelow.value = 5
  fileTotalLines.value = 0
  showHidden.value = false
  showExcludeForm.value = false
  showCurationForm.value = false
  showDecisionForm.value = false
  showReviewed.value = false
  if (pkg) {
    store.fetchPathExcludes(pkg.id)
    store.fetchCuration(pkg.id)
    store.fetchFindingCurations(pkg.id)
  }
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
      <!-- Root package list -->
      <template v-if="!currentPackage">
        <h1 class="text-xl font-semibold mb-4">Select a package to review</h1>
        <ul class="flex flex-col gap-1">
          <li v-for="rootId in store.rootPackageIds" :key="rootId">
            <button
              class="text-left px-3 py-2 border rounded w-full hover:bg-gray-50 font-mono text-sm"
              @click="navigateToRoot(store.packages.find((p) => p.id === rootId)?.purl ?? '')"
            >
              {{ rootId }}
            </button>
          </li>
        </ul>
      </template>

      <template v-else>
        <!-- Breadcrumb -->
        <nav
          v-if="navigationPath.length > 1"
          class="flex items-center gap-1 text-sm text-gray-500 mb-4 flex-wrap"
        >
          <template v-for="(purl, i) in navigationPath" :key="purl">
            <span v-if="i > 0" class="text-gray-300">/</span>
            <button
              v-if="i < navigationPath.length - 1"
              class="hover:underline"
              @click="router.push(purlPath(navigationPath.slice(0, i + 1)))"
            >
              {{ purlToPackage.get(purl)?.id ?? purl }}
            </button>
            <span v-else class="text-gray-800 font-medium">{{
              purlToPackage.get(purl)?.id ?? purl
            }}</span>
          </template>
        </nav>

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
              <th class="border px-3 py-1.5 text-left">Concluded license</th>
              <td class="border px-3 py-1.5">
                <template v-if="currentCuration?.concluded_license && !showCurationForm">
                  <span class="font-mono">{{ currentCuration.concluded_license }}</span>
                  <span v-if="currentCuration.comment" class="text-gray-400 ml-2 text-xs">{{
                    currentCuration.comment
                  }}</span>
                  <button
                    class="ml-2 text-xs border rounded px-1.5 py-0.5 text-gray-500 hover:bg-gray-50"
                    @click="openCurationForm"
                  >
                    Edit
                  </button>
                  <button
                    class="ml-1 text-xs text-gray-400 hover:text-red-500"
                    @click="store.removeCuration(currentPackage!.id)"
                  >
                    ✕
                  </button>
                </template>
                <template v-else-if="showCurationForm">
                  <div class="flex flex-wrap gap-2 items-center">
                    <input
                      v-model="curationLicense"
                      placeholder="SPDX expression"
                      class="border rounded px-2 py-0.5 text-xs font-mono"
                    />
                    <input
                      v-model="curationComment"
                      placeholder="Comment (optional)"
                      class="border rounded px-2 py-0.5 text-xs flex-1 min-w-0"
                    />
                    <button
                      class="text-xs border rounded px-2 py-0.5 bg-white hover:bg-gray-100"
                      @click="confirmCuration"
                    >
                      Confirm
                    </button>
                    <button
                      class="text-xs text-gray-400 hover:text-gray-600"
                      @click="showCurationForm = false"
                    >
                      Cancel
                    </button>
                  </div>
                </template>
                <template v-else>
                  <div class="flex flex-wrap gap-2 items-center">
                    <button
                      class="text-xs border rounded px-2 py-0.5 bg-green-50 text-green-700 border-green-300 hover:bg-green-100"
                      @click="openTrustForm"
                    >
                      Trust declared license
                    </button>
                    <button
                      class="ml-2 text-xs border rounded px-2 py-0.5 text-gray-500 hover:bg-gray-50"
                      @click="openCurationForm"
                    >
                      Conclude license
                    </button>
                  </div>
                </template>
              </td>
            </tr>
            <tr v-if="currentDeps.length">
              <th class="border px-3 py-1.5 text-left align-top">Dependencies</th>
              <td class="border px-3 py-1.5">
                <ul class="flex flex-col gap-0.5">
                  <li v-for="dep in currentDeps" :key="dep.id">
                    <button
                      class="font-mono text-xs hover:underline text-left"
                      @click="navigateToDep(dep.id)"
                    >
                      {{ dep.id }}
                    </button>
                  </li>
                </ul>
              </td>
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
          <div
            v-if="currentExcludes.length"
            class="text-xs border rounded px-3 py-2 mb-2 flex flex-col gap-1"
          >
            <span class="text-gray-500 font-medium"
              >Path excludes active for this package ({{ currentExcludes.length }}):</span
            >
            <div
              v-for="exc in currentExcludes"
              :key="exc.pattern"
              class="flex items-center gap-2"
            >
              <span class="font-mono text-gray-700">[{{ exc.pattern }}]</span>
              <span class="text-gray-500">{{ exc.reason }}</span>
              <button
                class="ml-auto text-gray-400 hover:text-red-500"
                @click="store.removePathExclude(currentPackage!.id, exc.pattern)"
              >
                ✕
              </button>
            </div>
          </div>
          <div v-if="totalFindings === 0 && allFindings.length" class="text-sm text-gray-500">
            No findings need review.
          </div>
          <template v-else-if="currentFinding">
            <div class="flex items-center justify-between mb-2">
              <h3 class="text-sm font-medium">
                Finding {{ findingIndex + 1 }} of {{ totalFindings
                }}<span
                  v-if="showExcludeForm && previewExcludeCount(excludeFormPattern) > 0"
                  class="text-gray-400 ml-1"
                  >−{{ previewExcludeCount(excludeFormPattern) }}</span
                >
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
                <template v-if="siblingFindingsInFile.length">
                  <span class="text-gray-300">|</span>
                  <span class="text-gray-400 text-xs">Also in file:</span>
                  <button
                    v-for="(f, i) in siblingFindingsInFile"
                    :key="i"
                    class="text-xs border rounded px-1.5 py-0.5 font-mono"
                    :class="
                      reviewFindings.indexOf(f) !== -1
                        ? 'text-gray-600 hover:bg-gray-100 cursor-pointer'
                        : 'text-gray-400 cursor-default'
                    "
                    :disabled="reviewFindings.indexOf(f) === -1"
                    @click="
                      reviewFindings.indexOf(f) !== -1 && (findingIndex = reviewFindings.indexOf(f))
                    "
                  >
                    {{ f.license }} | {{ f.score }}
                  </button>
                </template>
                <button
                  v-if="!showExcludeForm"
                  class="text-xs border rounded px-2 py-0.5 text-gray-500 hover:bg-gray-50"
                  @click="openExcludeForm"
                >
                  Exclude path
                </button>
                <template v-if="!showDecisionForm">
                  <button
                    class="text-xs border rounded px-2 py-0.5 bg-green-50 text-green-700 border-green-300 hover:bg-green-100"
                    @click="confirmFinding(currentFinding, currentFinding.license)"
                  >
                    Confirm as {{ currentFinding.license }}
                  </button>
                  <button
                    class="text-xs border rounded px-2 py-0.5 text-gray-500 hover:bg-gray-50"
                    @click="openDecisionForm"
                  >
                    Other…
                  </button>
                </template>
              </div>
              <div
                v-if="showDecisionForm"
                class="flex flex-wrap items-center gap-2 px-3 py-2 text-sm border-b bg-gray-50"
              >
                <input
                  v-model="decisionLicense"
                  placeholder="SPDX expression or NONE"
                  class="border rounded px-2 py-1 text-xs font-mono flex-1 min-w-0"
                />
                <DescribedSelect
                  v-model="decisionReason"
                  :options="LICENSE_FINDING_CURATIONS_REASONS"
                />
                <input
                  v-model="decisionComment"
                  placeholder="Comment (optional)"
                  class="border rounded px-2 py-1 text-xs flex-1 min-w-0"
                />
                <button
                  class="text-xs border rounded px-2 py-1 bg-white hover:bg-gray-100"
                  @click="confirmDecisionForm"
                >
                  Confirm
                </button>
                <button
                  class="text-xs text-gray-400 hover:text-gray-600"
                  @click="showDecisionForm = false"
                >
                  Cancel
                </button>
              </div>
              <div
                v-if="showExcludeForm"
                class="flex flex-wrap items-center gap-2 px-3 py-2 text-sm border-b bg-gray-50"
              >
                <select v-model="excludeFormPattern" class="border rounded px-2 py-1 text-xs">
                  <option
                    v-for="opt in pathExcludeOptions(currentFinding.location.path)"
                    :key="opt"
                    :value="opt"
                  >
                    {{ opt }}
                  </option>
                </select>
                <DescribedSelect v-model="excludeFormReason" :options="PATH_EXCLUDE_REASONS" />
                <input
                  v-model="excludeFormComment"
                  placeholder="Comment (optional)"
                  class="border rounded px-2 py-1 text-xs flex-1 min-w-0"
                />
                <button
                  class="text-xs border rounded px-2 py-1 bg-white hover:bg-gray-100"
                  @click="confirmExclude"
                >
                  Confirm
                </button>
                <button
                  class="text-xs text-gray-400 hover:text-gray-600"
                  @click="showExcludeForm = false"
                >
                  Cancel
                </button>
              </div>
              <div v-if="fileLoading" class="px-3 py-2 text-sm text-gray-400">Loading…</div>
              <div v-else-if="fileContent === null" class="px-3 py-2 text-sm text-red-400">
                Could not load file.
              </div>
              <pre
                v-else
                class="overflow-x-auto text-xs"
              ><button v-if="(fileContent[0]?.number ?? 0) > 1" type="button" class="w-full flex items-center gap-2 px-3 py-px bg-blue-50 hover:bg-blue-100 select-none text-blue-600" @click="expandAbove"><span class="text-gray-400 inline-block w-8 text-right">···</span><span>↑ Load 10 more lines</span></button><template v-for="line in fileContent" :key="line.number"><div :class="line.highlighted ? 'bg-yellow-100' : ''" class="px-3 py-px"><span class="select-none text-gray-400 mr-3 inline-block w-8 text-right">{{ line.number }}</span>{{ line.content }}</div></template><button v-if="(fileContent.at(-1)?.number ?? 0) < fileTotalLines" type="button" class="w-full flex items-center gap-2 px-3 py-px bg-blue-50 hover:bg-blue-100 select-none text-blue-600" @click="expandBelow"><span class="text-gray-400 inline-block w-8 text-right">···</span><span>↓ Load 10 more lines</span></button></pre>
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
          <div v-if="reviewedFindings.length" class="mt-3 flex flex-col gap-1">
            <div class="text-sm text-gray-400">
              {{ reviewedFindings.length }} finding{{ reviewedFindings.length === 1 ? '' : 's' }}
              marked as reviewed
              <button
                v-if="!showReviewed"
                class="ml-1 underline text-gray-500"
                @click="showReviewed = true"
              >
                show
              </button>
            </div>
            <div v-if="showReviewed">
              <button class="text-sm underline text-gray-500 mb-1" @click="showReviewed = false">
                hide
              </button>
              <div
                v-for="f in reviewedFindings"
                :key="findingCurationKey(f)"
                class="text-xs font-mono text-gray-500 px-1 flex items-center gap-2"
              >
                <span class="font-semibold">{{ f.license }}</span>
                {{ f.location.path }}:{{ f.location.start_line }}–{{ f.location.end_line }}
                <span class="text-green-700">
                  →
                  {{
                    currentFindingCurationsMap.get(findingCurationKey(f))?.concluded_license ?? '?'
                  }}
                </span>
                <span
                  v-if="currentFindingCurationsMap.get(findingCurationKey(f))?.comment"
                  class="text-gray-400"
                  >{{ currentFindingCurationsMap.get(findingCurationKey(f))?.comment }}</span
                >
                <button class="text-gray-400 hover:text-red-500" @click="removeFindingCuration(f)">
                  ✕
                </button>
              </div>
            </div>
          </div>
        </section>
      </template>
    </template>
  </main>
</template>
