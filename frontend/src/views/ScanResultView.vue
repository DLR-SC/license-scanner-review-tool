<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { useScanResultStore } from '@/stores/scanResult'

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
        </tbody>
      </table>
    </template>
  </main>
</template>
