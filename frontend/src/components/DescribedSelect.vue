<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

export interface Option {
  label: string
  description: string
}

defineProps<{ options: Option[] }>()
const model = defineModel<Option['label']>({ required: true })

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)

function onDocumentClick(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))
</script>

<template>
  <div class="relative" ref="rootRef">
    <button
      type="button"
      class="border rounded px-2 py-1 text-xs text-left bg-white flex items-center gap-1"
      @click.stop="open = !open"
    >
      {{ model }}
      <span class="text-gray-400">▾</span>
    </button>
    <ul
      v-if="open"
      class="absolute z-50 mt-1 w-80 bg-white border rounded shadow-lg max-h-72 overflow-y-auto"
    >
      <li
        v-for="option in options"
        :key="option.label"
        class="px-3 py-2 cursor-pointer hover:bg-gray-50"
        :class="{ 'bg-gray-100': model === option.label }"
        @click="
          () => {
            model = option.label
            open = false
          }
        "
      >
        <div class="text-xs font-medium">{{ option.label }}</div>
        <div class="text-xs text-gray-400 mt-0.5">{{ option.description }}</div>
      </li>
    </ul>
  </div>
</template>
