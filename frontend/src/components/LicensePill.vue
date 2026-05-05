<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
defineProps<{
  license: string
  score?: number
  clickable?: boolean
  disabled?: boolean
}>()

defineEmits<{
  click: []
}>()
</script>

<template>
  <component
    :is="clickable ? 'button' : 'div'"
    class="inline-flex items-center rounded-full text-xs font-mono overflow-hidden"
    :class="
      clickable && !disabled
        ? 'cursor-pointer hover:brightness-95'
        : clickable
          ? 'cursor-default opacity-50'
          : ''
    "
    :disabled="clickable ? disabled : undefined"
    @click="clickable && !disabled && $emit('click')"
  >
    <span class="bg-gray-200 text-gray-800 px-2 py-0.5">{{ license }}</span>
    <span v-if="score !== undefined" class="bg-gray-300 text-gray-600 px-2 py-0.5">{{
      score
    }}</span>
  </component>
</template>
