<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, useId } from 'vue'

export interface Option {
  label: string
  description?: string
}

const props = defineProps<{ options: (string | Option)[]; label?: string }>()

const normalizedOptions = computed(() =>
  props.options.map((o): Option => (typeof o === 'string' ? { label: o } : o)),
)
const model = defineModel<Option['label']>({ required: true })

const id = useId()
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
  <div class="flex flex-col gap-1" ref="rootRef">
    <label v-if="label" :for="id" class="text-xs text-gray-500 flex items-center gap-1"
      >{{ label }}<slot
    /></label>
    <div class="relative">
      <button
        :id="id"
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        :aria-expanded="open"
        class="border rounded px-2 py-1 text-sm text-left bg-white flex items-center gap-1"
        @click="open ? (open = false) : openDropdown()"
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
          v-for="option in normalizedOptions"
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
          <div v-if="option.description" class="text-xs text-gray-400 mt-0.5">
            {{ option.description }}
          </div>
        </button>
      </div>
    </div>
  </div>
</template>
