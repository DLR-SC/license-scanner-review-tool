<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref, computed, watch, onMounted, useTemplateRef } from 'vue'
import CarbonCheckmarkFilled from '~icons/carbon/checkmark-filled'
import CarbonTrashCan from '~icons/carbon/trash-can'
import AppButton from '@/components/AppButton.vue'
import CollapsiblePanel from '@/components/CollapsiblePanel.vue'
import InfoTooltip from '@/components/InfoTooltip.vue'
import AppInput from '@/components/AppInput.vue'
import SpdxInput from '@/components/SpdxInput.vue'
import { spdxMatchSet } from '@/utils/spdx'
import DescribedSelect from '@/components/DescribedSelect.vue'
import DependencyGraph from '@/components/DependencyGraph.vue'
import AppPanel from '@/components/AppPanel.vue'
import AppCard from '@/components/AppCard.vue'
import LicensePill from '@/components/LicensePill.vue'
import { useRoute } from 'vue-router'
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
import { api } from '@/api'

const store = useScanResultStore()
const route = useRoute()
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
function findingTier(f: LicenseFinding, licenseSet: Set<string>): number {
  const base = f.location.path.split('/').at(-1)?.toLowerCase() ?? ''
  if (base.endsWith('.gemspec') || MANIFEST_FILES.has(base)) return 0
  if (LICENSE_FILE_RE.test(base)) return 1
  if (!licenseSet.has(f.license)) return 2
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
  return store.packages.find((p) => decodeURIComponent(p.purl ?? '') === decoded) ?? null
})

const purlToPackage = computed(() => {
  // Key by decoded PURL so lookups work regardless of %40 vs @ encoding.
  const map = new Map<string, Package>()
  for (const p of store.packages) map.set(decodeURIComponent(p.purl ?? ''), p)
  return map
})

function purlPath(purls: string[]): string {
  return '/review/' + purls.join(';')
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
  () => store.scanResults.find((sr) => sr.packageId === currentPackage.value?.id) ?? null,
)

const detectedLicenses = computed(() => {
  const licenses = currentScanResult.value?.licenses ?? []
  return [...new Set(licenses.map((f) => f.license))].sort()
})

const findingIndex = ref(0)

const allFindings = computed(() => currentScanResult.value?.licenses ?? [])

const currentExcludes = computed(() => store.pathExcludes[currentPackage.value?.id ?? ''] ?? [])

const suggestedDeclaredLicense = ref('')

const effectiveSpdxExpression = computed(() => {
  if (suggestedDeclaredLicense.value) return suggestedDeclaredLicense.value
  return currentPackage.value?.declaredLicensesProcessed?.spdxExpression ?? ''
})

const reviewFindings = computed(() => {
  const licenseSet = spdxMatchSet(effectiveSpdxExpression.value)
  const excludePatterns = currentExcludes.value.map((e) => e.pattern)
  const curationsMap = currentFindingCurationsMap.value
  return allFindings.value
    .filter(
      (f) =>
        (f.score < 100 || !licenseSet.has(f.license)) &&
        !excludePatterns.some((p) => minimatch(f.location.path, p)) &&
        !curationsMap.has(findingCurationKey(f)),
    )
    .slice()
    .sort((a, b) => {
      const tierDiff = findingTier(a, licenseSet) - findingTier(b, licenseSet)
      return tierDiff !== 0 ? tierDiff : b.score - a.score
    })
})

const reviewedFindings = computed(() =>
  allFindings.value.filter((f) => currentFindingCurationsMap.value.has(findingCurationKey(f))),
)

const allDepsAndFindingsConcluded = computed(
  () =>
    currentDeps.value.every((dep) => !!store.curations[dep.id]?.concludedLicense) &&
    reviewFindings.value.length === 0,
)

const reviewedByLicense = computed(() => {
  const map = new Map<string, number>()
  for (const f of reviewedFindings.value) {
    map.set(f.license, (map.get(f.license) ?? 0) + 1)
  }
  return map
})

function previewExcludeCount(pattern: string): number {
  return reviewFindings.value.filter((f) => minimatch(f.location.path, pattern)).length
}

const hiddenFindings = computed(() =>
  allFindings.value.filter(
    (f) => f.score === 100 && effectiveSpdxExpression.value.includes(f.license),
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
        f.location.startLine === currentFinding.value!.location.startLine &&
        f.location.endLine === currentFinding.value!.location.endLine &&
        f.license === currentFinding.value!.license
      ),
  )
})

const showExcludeForm = ref(false)
const excludeFormPattern = ref('')
const excludeFormReason = ref<Option['label']>('BUILD_TOOL_OF')
const excludeFormComment = ref('')

const showCurationForm = ref(false)
const isTrustForm = ref(false)
const curationComment = ref('')
const curationLicense = ref('')

const currentCuration = computed(() => store.curations[currentPackage.value?.id ?? ''] ?? null)

function findingCurationKey(f: LicenseFinding): string {
  return `${f.location.path}:${f.location.startLine}:${f.license}`
}

const currentFindingCurations = computed(
  () => store.findingCurations[currentPackage.value?.id ?? ''] ?? [],
)

const currentFindingCurationsMap = computed(() => {
  const map = new Map<string, LicenseFindingCuration>()
  for (const c of currentFindingCurations.value) {
    map.set(`${c.path}:${c.startLines}:${c.detectedLicense}`, c)
  }
  return map
})

const showDecisionForm = ref(false)
const decisionLicense = ref('')
const decisionComment = ref('')
const decisionReason = ref<Option['label']>('CODE')

function openTrustForm() {
  isTrustForm.value = true
  curationLicense.value = currentPackage.value?.declaredLicensesProcessed?.spdxExpression ?? ''
  curationComment.value = 'Declared license is correct'
  showCurationForm.value = true
}

function openCurationForm() {
  isTrustForm.value = false
  curationLicense.value = currentCuration.value?.concludedLicense ?? ''
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

async function confirmDecisionForm() {
  if (!currentPackage.value || !currentFinding.value) return
  await store.setFindingCuration(currentPackage.value.id, {
    path: currentFinding.value.location.path,
    startLines: String(currentFinding.value.location.startLine),
    lineCount: currentFinding.value.location.endLine - currentFinding.value.location.startLine + 1,
    detectedLicense: currentFinding.value.license,
    reason: decisionReason.value,
    comment: decisionComment.value,
    concludedLicense: decisionLicense.value,
  })
  showDecisionForm.value = false
}

const includedLicenses = computed<string[]>(() => {
  const licenses = new Set<string>()
  const spdx = effectiveSpdxExpression.value
  if (spdx) licenses.add(spdx)
  for (const c of currentFindingCurations.value) {
    if (c.concludedLicense) licenses.add(c.concludedLicense)
  }
  for (const dep of currentDeps.value) {
    const concluded = store.curations[dep.id]?.concludedLicense
    if (concluded) licenses.add(concluded)
  }
  return [...licenses].filter((l) => l !== 'NONE').sort() // NONE means "no license found" for license findings
})

const suggestedConcludeLicense = computed(() =>
  // concluding to NOASSERTION is not very useful, so suggest NONE instead since often NOASSERTION is detected when no license text is found at all
  currentFinding.value?.license === 'NOASSERTION' ? 'NONE' : (currentFinding.value?.license ?? ''),
)

function openDecisionForm(prefillLicense?: string) {
  if (!currentFinding.value) return
  decisionLicense.value = prefillLicense ?? ''
  decisionComment.value = ''
  decisionReason.value = currentFinding.value.license === 'NOASSERTION' ? 'REFERENCE' : 'CODE'
  showDecisionForm.value = true
}

async function removeFindingCuration(f: LicenseFinding) {
  if (!currentPackage.value) return
  await store.removeFindingCuration(
    currentPackage.value.id,
    f.location.path,
    String(f.location.startLine),
    f.license,
  )
}

const fileContent = ref<Array<{ number: number; content: string; highlighted: boolean }> | null>(
  null,
)
const fileLoading = ref(false)
const fileContentEl = useTemplateRef('fileContentEl')
const fileLoadingHeight = ref(0)
const contextAbove = ref(5)
const contextBelow = ref(5)
const fileTotalLines = ref(0)

async function loadFinding(finding: LicenseFinding) {
  fileLoadingHeight.value = fileContentEl.value?.clientHeight ?? 0
  fileContent.value = null
  fileLoading.value = true
  try {
    const data = await api.getFileContent({
      packageId: currentPackage.value!.id,
      path: finding.location.path,
      startLine: finding.location.startLine,
      endLine: finding.location.endLine,
      contextBefore: contextAbove.value,
      contextAfter: contextBelow.value,
    })
    fileContent.value = data.lines
    fileTotalLines.value = data.totalLines ?? 0
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
  return f.location.endLine - f.location.startLine > 3
}

const canonicalText = ref<string | null>(null)
const canonicalLoading = ref(false)

async function loadCanonicalText(license: string) {
  canonicalText.value = null
  canonicalLoading.value = true
  try {
    const data = await api.getLicenseText({ license })
    canonicalText.value = data.text ?? null
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
  showExcludeForm.value = false
  showCurationForm.value = false
  isTrustForm.value = false
  showDecisionForm.value = false
  suggestedDeclaredLicense.value = ''
  if (pkg) {
    store.fetchPathExcludes(pkg.id)
    store.fetchCuration(pkg.id)
    store.fetchFindingCurations(pkg.id)
  }
})

const vcsSiblings = computed(() => currentPackage.value?.vcsSiblings ?? [])

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
      const data = await api.getDownloads({ purl: pkg.purl })
      weeklyDownloads.value = data.weeklyDownloads ?? null
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
    if (!pkg?.vcsUrl) return
    starsLoading.value = true
    try {
      const data = await api.getGithubStars({ url: pkg.vcsUrl })
      githubStars.value = data.stars ?? null
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
            <RouterLink
              class="text-left px-3 py-2 border rounded w-full hover:bg-gray-50 font-mono text-sm flex items-center gap-2"
              :to="purlPath([store.packages.find((p) => p.id === rootId)?.purl ?? ''])"
            >
              <CarbonCheckmarkFilled
                :class="
                  store.curations[rootId]?.concludedLicense ? 'text-green-500' : 'text-gray-300'
                "
                aria-hidden="true"
              />
              {{ rootId }}
            </RouterLink>
          </li>
        </ul>
      </template>

      <template v-else>
        <!-- Breadcrumb -->
        <nav
          v-if="navigationPath.length > 0"
          class="flex items-center gap-1 text-sm text-gray-500 mb-4 flex-wrap"
        >
          <RouterLink to="/review/" class="hover:underline">Your project</RouterLink>
          <template v-for="(purl, i) in navigationPath" :key="purl">
            <span class="text-gray-300">/</span>
            <RouterLink
              v-if="i < navigationPath.length - 1"
              class="hover:underline"
              :to="purlPath(navigationPath.slice(0, i + 1))"
            >
              {{ purlToPackage.get(purl)?.id ?? purl }}
            </RouterLink>
            <span v-else class="text-gray-800 font-medium">{{
              purlToPackage.get(purl)?.id ?? purl
            }}</span>
          </template>
        </nav>

        <div class="flex gap-4 mb-4">
          <AppPanel
            title="Package metadata"
            tooltip="General information about this package: its identifier, source repository, declared and detected licenses, dependencies, and popularity metrics."
            class="flex-1 min-w-0"
          >
            <div>
              <table v-if="currentPackage" class="text-sm w-full">
                <tbody class="divide-y divide-gray-100">
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 w-40">ID</th>
                    <td class="px-4 py-2">{{ currentPackage.id }}</td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">PURL</th>
                    <td class="px-4 py-2">{{ currentPackage.purl }}</td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Registry</th>
                    <td class="px-4 py-2">
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
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">
                      Description
                    </th>
                    <td class="px-4 py-2">{{ currentPackage.description }}</td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Homepage</th>
                    <td class="px-4 py-2">
                      <a
                        v-if="currentPackage.homepageUrl"
                        :href="currentPackage.homepageUrl"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="underline"
                        >{{ currentPackage.homepageUrl }}</a
                      >
                    </td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">VCS</th>
                    <td class="px-4 py-2">
                      <a
                        v-if="currentPackage.vcsUrl"
                        :href="currentPackage.vcsUrl"
                        target="_blank"
                        rel="noopener noreferrer"
                        class="underline"
                        >{{ currentPackage.vcsUrl }}</a
                      >
                    </td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">Authors</th>
                    <td class="px-4 py-2">{{ currentPackage.authors?.join(', ') }}</td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">
                      Declared licenses
                    </th>
                    <td class="px-4 py-2 flex flex-wrap gap-1 items-center">
                      <InfoTooltip
                        v-if="!currentPackage.declaredLicensesProcessed?.spdxExpression"
                        warning
                        :text="
                          (currentPackage.declaredLicenses?.length ?? 0) === 0
                            ? 'No declared license found'
                            : 'Not a valid SPDX expression'
                        "
                      />
                      <LicensePill
                        v-if="currentPackage.declaredLicensesProcessed?.spdxExpression"
                        :license="currentPackage.declaredLicensesProcessed.spdxExpression"
                      />
                      <template v-else>
                        <LicensePill
                          v-for="l in currentPackage.declaredLicenses"
                          :key="l"
                          :license="l"
                        />
                      </template>
                    </td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">
                      Detected licenses
                    </th>
                    <td class="px-4 py-2">
                      <div class="flex flex-wrap gap-1">
                        <LicensePill v-for="l in detectedLicenses" :key="l" :license="l" />
                      </div>
                    </td>
                  </tr>
                  <tr v-if="currentDeps.length">
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500 align-top">
                      Dependencies
                    </th>
                    <td class="px-4 py-2">
                      <ul class="flex flex-col gap-0.5">
                        <li v-for="dep in currentDeps" :key="dep.id">
                          <RouterLink
                            class="font-mono text-xs hover:underline text-left flex items-center gap-1.5"
                            :to="
                              purlPath([
                                ...navigationPath,
                                store.packages.find((p) => p.id === dep.id)?.purl ?? '',
                              ])
                            "
                          >
                            <CarbonCheckmarkFilled
                              :class="
                                store.curations[dep.id]?.concludedLicense
                                  ? 'text-green-500'
                                  : 'text-gray-300'
                              "
                              aria-hidden="true"
                            />
                            {{ dep.id }}
                          </RouterLink>
                        </li>
                      </ul>
                    </td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">
                      Weekly downloads
                    </th>
                    <td class="px-4 py-2">
                      <span v-if="downloadsLoading">…</span>
                      <span v-else-if="weeklyDownloads !== null">{{
                        weeklyDownloads.toLocaleString()
                      }}</span>
                      <span v-else>—</span>
                    </td>
                  </tr>
                  <tr>
                    <th class="px-4 py-2 text-left text-xs font-medium text-gray-500">
                      GitHub stars
                    </th>
                    <td class="px-4 py-2">
                      <span v-if="starsLoading">…</span>
                      <span v-else-if="githubStars !== null">{{
                        githubStars.toLocaleString()
                      }}</span>
                      <span v-else>—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </AppPanel>
          <AppPanel
            title="Dependency Graph"
            tooltip="Visual overview of the dependency tree useful to orient yourself while reviewing the packages and to see the progress you've made. The tree starts with the root project at the top. Packages with concluded licenses are marked green, the currently selected package is highlighted with a blue border. Hovering over a node shows the package name."
            class="shrink-0"
          >
            <DependencyGraph :current-package-id="currentPackage!.id" />
          </AppPanel>
        </div>

        <!-- License conclusion panel -->
        <div
          class="border-2 rounded-lg overflow-hidden mt-4"
          :class="
            currentCuration?.concludedLicense && !showCurationForm
              ? 'border-green-400 shadow-sm'
              : 'border-blue-400 shadow-md'
          "
        >
          <div
            class="px-4 py-3 flex items-center gap-2"
            :class="
              currentCuration?.concludedLicense && !showCurationForm
                ? 'bg-green-100'
                : 'bg-blue-100'
            "
          >
            <CarbonCheckmarkFilled
              v-if="currentCuration?.concludedLicense && !showCurationForm"
              class="w-5 h-5 text-green-600"
              aria-hidden="true"
            />
            <h2 class="text-base font-semibold">
              {{
                currentCuration?.concludedLicense && !showCurationForm
                  ? 'License concluded'
                  : 'Conclude license'
              }}
            </h2>
          </div>
          <div
            class="px-4 py-4 flex flex-col gap-3"
            :class="currentCuration?.concludedLicense && !showCurationForm ? 'bg-green-50' : ''"
          >
            <template v-if="currentCuration?.concludedLicense && !showCurationForm">
              <p class="text-sm text-green-800">
                The license of this package has been concluded. You can now go back to the parent
                package to continue your review there.
              </p>
              <div class="flex items-baseline gap-3">
                <LicensePill :license="currentCuration.concludedLicense!" />
                <span v-if="currentCuration.comment" class="text-gray-500 text-xs">{{
                  currentCuration.comment
                }}</span>
                <div class="ml-auto flex items-center gap-1 shrink-0">
                  <AppButton @click="openCurationForm">Edit</AppButton>
                  <AppButton
                    variant="danger"
                    class="inline-flex items-center gap-1.5"
                    @click="store.removeCuration(currentPackage!.id)"
                  >
                    <CarbonTrashCan class="w-4 h-4" />Delete
                  </AppButton>
                </div>
              </div>
            </template>
            <template v-else-if="showCurationForm">
              <div
                v-if="isTrustForm"
                class="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2"
              >
                Only use this option when you are really confident that the declared license is
                reliable and correct.
              </div>
              <div
                v-else
                class="text-sm text-blue-800 bg-blue-50 border border-blue-200 rounded px-3 py-2"
              >
                Ensure that all licenses included by your review are compatible with the license you
                are about to conclude. Refer to the
                <a
                  href="https://www.dlr.de/de/sc/medien/publikationen/broschuere-open-source-software-im-dlr"
                  target="_blank"
                  rel="noopener noreferrer"
                  class="underline font-medium"
                  >DLR Open Source compatibility guide</a
                >
                for compatibility analysis.
              </div>
              <div v-if="includedLicenses.length" class="flex flex-wrap items-center gap-2">
                <span class="text-xs text-gray-500 shrink-0 flex items-center gap-1">
                  Included licenses after review
                  <InfoTooltip
                    text="Use this as a guide when concluding the overall license for this package. The list includes the declared license, any licenses concluded for individual findings, and the concluded licenses of all direct dependencies."
                  />
                </span>
                <LicensePill
                  v-for="license in includedLicenses"
                  :key="license"
                  :license="license"
                />
              </div>
              <div class="flex flex-wrap gap-2 items-end">
                <SpdxInput
                  v-model="curationLicense"
                  label="License"
                  placeholder="SPDX expression"
                  class="flex-1 min-w-0"
                />
                <AppInput
                  v-model="curationComment"
                  label="Comment"
                  placeholder="Optional"
                  class="flex-1 min-w-0"
                />
                <AppButton @click="confirmCuration">Confirm</AppButton>
                <AppButton variant="text" @click="showCurationForm = false">Cancel</AppButton>
              </div>
            </template>
            <template v-else>
              <p v-if="allDepsAndFindingsConcluded" class="text-sm font-medium text-gray-800">
                All findings and dependencies have been reviewed. Conclude the license for this
                package now based on your review.
              </p>
              <p v-else class="text-sm text-gray-600">
                Review the license findings and child dependencies in the panel below, then return
                here to conclude the license. Alternatively, trust the declared license if you are
                confident it is correct based on the package's popularity metadata.
              </p>
              <div class="flex items-center gap-2">
                <AppButton
                  v-if="currentPackage.declaredLicensesProcessed?.spdxExpression"
                  @click="openTrustForm"
                >
                  Trust declared license
                </AppButton>
                <AppButton variant="primary" @click="openCurationForm">Conclude license</AppButton>
              </div>
              <div v-if="includedLicenses.length" class="flex flex-wrap items-center gap-2">
                <span class="text-xs text-gray-500 shrink-0 flex items-center gap-1">
                  Included licenses after review
                  <InfoTooltip
                    text="Use this as a guide when concluding the overall license for this package. The list includes the declared license, any licenses concluded for individual findings, and the concluded licenses of all direct dependencies."
                  />
                </span>
                <LicensePill
                  v-for="license in includedLicenses"
                  :key="license"
                  :license="license"
                />
              </div>
            </template>
          </div>
        </div>

        <!-- License findings panel -->
        <AppPanel
          title="License findings"
          tooltip="Review the license findings and the dependencies before concluding the license for this package. For each finding you can view the detected license text in context, compare it to a canonical version of the license, and then decide to exclude the file from the scan results or to conclude a specific license for the finding."
          class="mt-4"
        >
          <div class="px-4 py-3">
            <SpdxInput
              v-model="suggestedDeclaredLicense"
              label="Suggested declared license"
              placeholder="SPDX expression"
              class="w-2xl"
            >
              <InfoTooltip
                text="In case the declared license is missing or not a valid SPDX expression, you can suggest a license expression to help reduce the number of findings that need review. This does not change the declared license in the data, it's just a hint for the review process."
              />
            </SpdxInput>
          </div>
          <div
            v-if="allFindings.length"
            class="px-4 py-3 border-t border-gray-100 flex flex-col gap-2"
          >
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
            <div
              v-if="currentExcludes.length || hiddenByLicense.size || reviewedFindings.length"
              :key="currentPackage?.id"
              class="flex flex-col gap-2"
            >
              <CollapsiblePanel v-if="hiddenByLicense.size">
                <template #summary>
                  <span class="text-gray-600"
                    >{{ hiddenFindings.length }} hidden finding{{
                      hiddenFindings.length === 1 ? '' : 's'
                    }}<span class="text-gray-400">
                      ·
                      {{
                        Array.from(hiddenByLicense)
                          .map(([l, c]) => `${l} (${c})`)
                          .join(', ')
                      }}
                    </span></span
                  >
                  <InfoTooltip
                    text="Findings with a confidence score of 100 whose license is already covered by the package's declared license expression or the license you suggested instead. They don't require review."
                  />
                </template>
                <table class="w-full text-sm">
                  <thead class="bg-gray-50 border-b text-xs text-gray-400">
                    <tr>
                      <th class="px-3 py-1.5 text-left font-medium">License finding</th>
                      <th class="px-3 py-1.5 text-left font-medium">Location</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-100">
                    <tr
                      v-for="f in hiddenFindings"
                      :key="`${f.location.path}:${f.location.startLine}`"
                    >
                      <td class="px-3 py-2">
                        <LicensePill :license="f.license" :score="f.score" />
                      </td>
                      <td class="px-3 py-2 font-mono text-gray-500">
                        {{ f.location.path }}:{{ f.location.startLine }}–{{ f.location.endLine }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </CollapsiblePanel>

              <CollapsiblePanel v-if="reviewedFindings.length">
                <template #summary>
                  <span class="text-gray-600"
                    >{{ reviewedFindings.length }} reviewed finding{{
                      reviewedFindings.length === 1 ? '' : 's'
                    }}<span class="text-gray-400">
                      ·
                      {{
                        Array.from(reviewedByLicense)
                          .map(([l, c]) => `${l} (${c})`)
                          .join(', ')
                      }}
                    </span></span
                  >
                </template>
                <table class="w-full text-sm">
                  <thead class="bg-gray-50 border-b text-xs text-gray-400">
                    <tr>
                      <th class="px-3 py-1.5 text-left font-medium">License finding</th>
                      <th class="px-3 py-1.5 text-left font-medium">Location</th>
                      <th class="px-3 py-1.5 text-left font-medium">Concluded license</th>
                      <th class="px-3 py-1.5 text-left font-medium">Comment</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-100">
                    <tr v-for="f in reviewedFindings" :key="findingCurationKey(f)">
                      <td class="px-3 py-2">
                        <LicensePill :license="f.license" :score="f.score" />
                      </td>
                      <td class="px-3 py-2 font-mono text-gray-500">
                        {{ f.location.path }}:{{ f.location.startLine }}–{{ f.location.endLine }}
                      </td>
                      <td class="px-3 py-2 text-green-700">
                        {{
                          currentFindingCurationsMap.get(findingCurationKey(f))?.concludedLicense ??
                          '?'
                        }}
                      </td>
                      <td class="px-3 py-2 text-gray-400">
                        {{ currentFindingCurationsMap.get(findingCurationKey(f))?.comment }}
                      </td>
                      <td class="px-3 py-2 text-right">
                        <AppButton
                          variant="danger"
                          title="Remove finding conclusion"
                          @click="removeFindingCuration(f)"
                        >
                          <CarbonTrashCan class="w-4 h-4" />
                        </AppButton>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </CollapsiblePanel>

              <CollapsiblePanel v-if="currentExcludes.length">
                <template #summary>
                  <span class="text-gray-600"
                    >{{ currentExcludes.length }} path exclude{{
                      currentExcludes.length === 1 ? '' : 's'
                    }}</span
                  >
                </template>
                <table class="w-full text-sm">
                  <thead class="bg-gray-50 border-b text-xs text-gray-400">
                    <tr>
                      <th class="px-3 py-1.5 text-left font-medium">Path Pattern</th>
                      <th class="px-3 py-1.5 text-left font-medium">Reason</th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-gray-100">
                    <tr v-for="exc in currentExcludes" :key="exc.pattern">
                      <td class="px-3 py-2 font-mono text-gray-700">{{ exc.pattern }}</td>
                      <td class="px-3 py-2 text-gray-400">{{ exc.reason }}</td>
                      <td class="px-3 py-2 text-right">
                        <AppButton
                          variant="danger"
                          title="Remove path exclude"
                          @click="store.removePathExclude(currentPackage!.id, exc.pattern)"
                        >
                          <CarbonTrashCan class="w-4 h-4" />
                        </AppButton>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </CollapsiblePanel>
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
                  <AppButton :disabled="findingIndex === 0" @click="findingIndex--"
                    >← Prev</AppButton
                  >
                  <AppButton :disabled="findingIndex >= totalFindings - 1" @click="findingIndex++"
                    >Next →</AppButton
                  >
                </div>
              </div>
              <AppCard>
                <template #title>
                  <div class="flex items-center gap-3 text-sm h-8">
                    <LicensePill :license="currentFinding.license" :score="currentFinding.score" />
                    <span class="text-gray-500"
                      >{{ currentFinding.location.path }}:{{ currentFinding.location.startLine }}–{{
                        currentFinding.location.endLine
                      }}</span
                    >
                    <AppButton v-if="!showDecisionForm && !showExcludeForm" @click="openExcludeForm"
                      >Exclude path</AppButton
                    >
                    <template v-if="!showDecisionForm && !showExcludeForm">
                      <AppButton
                        variant="primary"
                        @click="openDecisionForm(suggestedConcludeLicense)"
                      >
                        Conclude as {{ suggestedConcludeLicense }}
                      </AppButton>
                      <AppButton @click="openDecisionForm()">Conclude another license</AppButton>
                    </template>
                  </div>
                </template>
                <div
                  v-if="showDecisionForm"
                  class="flex flex-wrap items-end gap-2 px-3 py-2 text-sm border-b bg-gray-50"
                >
                  <SpdxInput
                    v-model="decisionLicense"
                    label="License"
                    placeholder="SPDX expression or NONE"
                    class="flex-1 min-w-0"
                    allow-none
                  />
                  <DescribedSelect
                    v-model="decisionReason"
                    :options="LICENSE_FINDING_CURATIONS_REASONS"
                    label="Reason"
                  />
                  <AppInput
                    v-model="decisionComment"
                    label="Comment"
                    placeholder="Optional"
                    class="flex-1 min-w-0"
                  />
                  <AppButton @click="confirmDecisionForm">Conclude</AppButton>
                  <AppButton variant="text" @click="showDecisionForm = false">Cancel</AppButton>
                </div>
                <div
                  v-if="showExcludeForm"
                  class="flex flex-wrap items-end gap-2 px-3 py-2 text-sm border-b bg-gray-50"
                >
                  <DescribedSelect
                    v-model="excludeFormPattern"
                    :options="pathExcludeOptions(currentFinding.location.path)"
                    label="Path pattern"
                  />
                  <DescribedSelect
                    v-model="excludeFormReason"
                    :options="PATH_EXCLUDE_REASONS"
                    label="Reason"
                  />
                  <AppInput
                    v-model="excludeFormComment"
                    label="Comment"
                    placeholder="Optional"
                    class="flex-1 min-w-0"
                  />
                  <AppButton @click="confirmExclude">Confirm</AppButton>
                  <AppButton variant="text" @click="showExcludeForm = false">Cancel</AppButton>
                </div>
                <div
                  v-if="fileLoading && fileContent === null"
                  class="animate-pulse bg-gray-100"
                  :style="fileLoadingHeight ? `height: ${fileLoadingHeight}px` : 'height: 8rem'"
                />
                <div
                  v-else-if="!fileLoading && fileContent === null"
                  class="px-3 py-2 text-sm text-red-400"
                >
                  Could not load file.
                </div>
                <pre
                  v-if="fileContent !== null"
                  ref="fileContentEl"
                  class="overflow-x-auto text-xs"
                ><button v-if="(fileContent[0]?.number ?? 0) > 1" type="button" class="w-full flex items-center gap-2 px-3 py-px bg-blue-50 hover:bg-blue-100 select-none text-blue-600" @click="expandAbove"><span class="text-gray-400 inline-block w-8 text-right">···</span><span>↑ Load 10 more lines</span></button><template v-for="line in fileContent" :key="line.number"><div :class="line.highlighted ? 'bg-yellow-100' : ''" class="px-3 py-px"><span class="select-none text-gray-400 mr-3 inline-block w-8 text-right">{{ line.number }}</span>{{ line.content }}</div></template><button v-if="(fileContent.at(-1)?.number ?? 0) < fileTotalLines" type="button" class="w-full flex items-center gap-2 px-3 py-px bg-blue-50 hover:bg-blue-100 select-none text-blue-600" @click="expandBelow"><span class="text-gray-400 inline-block w-8 text-right">···</span><span>↓ Load 10 more lines</span></button></pre>
                <div
                  v-if="siblingFindingsInFile.length"
                  class="flex flex-wrap items-center gap-2 px-3 py-2 text-sm border-t"
                >
                  <span class="text-gray-900 text-xs">Other license findings in this file:</span>
                  <LicensePill
                    v-for="(f, i) in siblingFindingsInFile"
                    :key="i"
                    clickable
                    :license="f.license"
                    :score="f.score"
                    :disabled="reviewFindings.indexOf(f) === -1"
                    @click="findingIndex = reviewFindings.indexOf(f)"
                  />
                </div>
              </AppCard>
              <div v-if="canonicalLoading" class="text-sm text-gray-400 mt-2">
                Loading canonical text…
              </div>
              <AppCard v-else-if="wordDiff" class="mt-2">
                <template #title>
                  <span class="text-sm text-gray-600"
                    >Diff vs. canonical
                    <span class="font-mono">{{ currentFinding.license }}</span></span
                  >
                </template>
                <pre
                  class="overflow-x-auto text-xs px-3 py-2"
                ><template v-for="(change, i) in wordDiff" :key="i"><span :class="{
                'bg-green-100 text-green-800': change.added,
                'bg-red-100 text-red-700 line-through': change.removed,
              }">{{ change.value }}</span></template></pre>
              </AppCard>
            </template>
          </div>
        </AppPanel>
      </template>
    </template>
  </main>
</template>
