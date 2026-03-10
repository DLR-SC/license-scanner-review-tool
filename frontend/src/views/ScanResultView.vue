<script setup lang="ts">
import { onMounted } from 'vue'
import { useScanResultStore } from '@/stores/scanResult'

const store = useScanResultStore()
onMounted(() => store.fetchScanResult())
</script>

<template>
  <main>
    <h1>Scan Result</h1>

    <div v-if="store.loading">Loading…</div>
    <div v-else-if="store.error" class="text-red-500">Error: {{ store.error }}</div>

    <template v-else-if="store.repository">
      <section class="mb-8">
        <h2>Repository</h2>
        <table class="border-collapse w-full text-sm">
          <tbody>
            <tr><th class="border px-3 py-1.5 text-left">URL</th><td class="border px-3 py-1.5 text-left">{{ store.repository.vcs_processed.url }}</td></tr>
            <tr><th class="border px-3 py-1.5 text-left">Revision</th><td class="border px-3 py-1.5 text-left">{{ store.repository.vcs_processed.revision }}</td></tr>
            <tr><th class="border px-3 py-1.5 text-left">Type</th><td class="border px-3 py-1.5 text-left">{{ store.repository.vcs_processed.type }}</td></tr>
          </tbody>
        </table>
      </section>

      <section class="mb-8">
        <h2>Projects ({{ store.projects.length }})</h2>
        <table class="border-collapse w-full text-sm">
          <thead>
            <tr>
              <th class="border px-3 py-1.5 text-left">ID</th>
              <th class="border px-3 py-1.5 text-left">Definition file</th>
              <th class="border px-3 py-1.5 text-left">Declared licenses</th>
              <th class="border px-3 py-1.5 text-left">Scopes</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="p in store.projects" :key="p.id">
              <td class="border px-3 py-1.5 text-left">{{ p.id }}</td>
              <td class="border px-3 py-1.5 text-left">{{ p.definition_file_path }}</td>
              <td class="border px-3 py-1.5 text-left">{{ p.declared_licenses_processed.spdx_expression || p.declared_licenses.join(', ') }}</td>
              <td class="border px-3 py-1.5 text-left">{{ p.scope_names.join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="mb-8">
        <h2>Packages ({{ store.packages.length }})</h2>
        <table class="border-collapse w-full text-sm">
          <thead>
            <tr>
              <th class="border px-3 py-1.5 text-left">ID</th>
              <th class="border px-3 py-1.5 text-left">Declared license (SPDX)</th>
              <th class="border px-3 py-1.5 text-left">Description</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="pkg in store.packages" :key="pkg.id">
              <td class="border px-3 py-1.5 text-left">{{ pkg.id }}</td>
              <td class="border px-3 py-1.5 text-left">{{ pkg.declared_licenses_processed.spdx_expression }}</td>
              <td class="border px-3 py-1.5 text-left">{{ pkg.description }}</td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="mb-8">
        <h2>Detected licenses by package ({{ store.scanResults.length }})</h2>
        <table class="border-collapse w-full text-sm">
          <thead>
            <tr>
              <th class="border px-3 py-1.5 text-left">Repository</th>
              <th class="border px-3 py-1.5 text-left">Revision</th>
              <th class="border px-3 py-1.5 text-left">Licenses found</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(sr, i) in store.scanResults" :key="i">
              <td class="border px-3 py-1.5 text-left">{{ sr.provenance.vcs_info.url }}</td>
              <td class="border px-3 py-1.5 text-left">{{ sr.provenance.resolved_revision.slice(0, 8) }}</td>
              <td class="border px-3 py-1.5 text-left">{{ [...new Set(sr.licenses.map((l) => l.license))].join(', ') }}</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
  </main>
</template>
