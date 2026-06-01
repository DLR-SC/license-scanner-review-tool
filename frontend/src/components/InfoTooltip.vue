<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted, useTemplateRef, useId } from 'vue'
import CarbonInformationFilled from '~icons/carbon/information-filled'

defineProps<{ text?: string; warning?: boolean }>()

const pinned = ref(false)
const hovered = ref(false)
const root = ref<HTMLElement | null>(null)
const tooltipEl = useTemplateRef('tooltipEl')
const offsetX = ref(0)
const flipped = ref(false)
const tooltipId = useId()

const visible = computed(() => pinned.value || hovered.value)

watch(
  visible,
  async (v) => {
    if (!v) return
    offsetX.value = 0
    flipped.value = false
    await nextTick()
    if (!tooltipEl.value) return
    const rect = tooltipEl.value.getBoundingClientRect()
    const margin = 8
    if (rect.top < margin) flipped.value = true
    if (rect.right > window.innerWidth - margin)
      offsetX.value = window.innerWidth - margin - rect.right
    if (rect.left < margin) offsetX.value = margin - rect.left
  },
  { flush: 'post' },
)

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
    <button
      type="button"
      :aria-describedby="visible ? tooltipId : undefined"
      class="cursor-pointer rounded focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-gray-400"
      @mouseenter="show"
      @mouseleave="hide"
      @click.stop="toggle"
      @keydown.space.stop="toggle"
      @keydown.enter.stop="toggle"
      @keydown.escape.stop="pinned = false"
    >
      <CarbonInformationFilled
        :class="warning ? 'text-yellow-600' : 'text-gray-400'"
        aria-hidden="true"
      />
      <span class="sr-only">More information</span>
    </button>
    <span
      v-if="visible"
      :id="tooltipId"
      ref="tooltipEl"
      role="tooltip"
      class="absolute left-1/2 z-10 w-max max-w-xs rounded bg-gray-800 px-2.5 py-1.5 text-sm text-white shadow-md"
      :class="flipped ? 'top-full mt-1.5' : 'bottom-full mb-1.5'"
      :style="{ transform: `translateX(calc(-50% + ${offsetX}px))` }"
    >
      <slot>{{ text }}</slot>
      <span
        v-if="flipped"
        class="absolute bottom-full left-1/2 border-4 border-transparent border-b-gray-800"
        :style="{ transform: `translateX(calc(-50% + ${-offsetX}px))` }"
      />
      <span
        v-else
        class="absolute top-full left-1/2 border-4 border-transparent border-t-gray-800"
        :style="{ transform: `translateX(calc(-50% + ${-offsetX}px))` }"
      />
    </span>
  </span>
</template>
