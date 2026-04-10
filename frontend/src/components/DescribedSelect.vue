<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

export interface Option {
  label: string
  description: string
}

defineProps<{ options: Option[] }>()
const model = defineModel<Option['label']>({ required: true })

const open = ref(false)
const rootRef = ref<HTMLElement | null>(null)
const listboxRef = ref<HTMLElement | null>(null)

function onDocumentClick(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}
onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))

async function openDropdown() {
  open.value = true
  await nextTick()
  const first = listboxRef.value?.querySelector<HTMLElement>('button')
  first?.focus()
}
</script>

<template>
  <div class="relative" ref="rootRef">
    <button
      type="button"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      class="border rounded px-2 py-1 text-xs text-left bg-white flex items-center gap-1"
      @click.stop="open ? (open = false) : openDropdown()"
    >
      {{ model }}
      <span class="text-gray-400">▾</span>
    </button>
    <div
      v-if="open"
      ref="listboxRef"
      role="listbox"
      class="absolute z-50 mt-1 w-80 bg-white border rounded shadow-lg max-h-72 overflow-y-auto"
    >
      <button
        v-for="option in options"
        :key="option.label"
        type="button"
        role="option"
        :aria-selected="model === option.label"
        class="w-full px-3 py-2 text-left cursor-pointer hover:bg-gray-50"
        :class="{ 'bg-gray-100': model === option.label }"
        @click="
          () => {
            model = option.label
            open = false
          }
        "
        @keydown.esc="open = false"
      >
        <div class="text-xs font-medium">{{ option.label }}</div>
        <div class="text-xs text-gray-400 mt-0.5">{{ option.description }}</div>
      </button>
    </div>
  </div>
</template>
