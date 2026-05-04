<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import CarbonInformationFilled from '~icons/carbon/information-filled'

defineProps<{ text: string }>()

const pinned = ref(false)
const hovered = ref(false)
const root = ref<HTMLElement | null>(null)

const show = () => (hovered.value = true)
const hide = () => (hovered.value = false)
const toggle = () => (pinned.value = !pinned.value)

function onClickOutside(e: MouseEvent) {
  if (pinned.value && root.value && !root.value.contains(e.target as Node)) {
    pinned.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<template>
  <span ref="root" class="relative inline-flex items-center">
    <CarbonInformationFilled
      class="text-yellow-600 cursor-pointer"
      aria-hidden="true"
      @mouseenter="show"
      @mouseleave="hide"
      @click.stop="toggle"
    />
    <span
      v-if="pinned || hovered"
      class="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 z-10 w-max max-w-56 rounded bg-gray-800 px-2.5 py-1.5 text-sm text-white shadow-md"
      role="tooltip"
    >
      {{ text }}
      <span
        class="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-800"
      />
    </span>
  </span>
</template>
