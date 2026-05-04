<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import InfoTooltip from '@/components/InfoTooltip.vue'

defineProps<{
  title: string
  tooltip?: string
}>()
</script>

<template>
  <div class="border rounded flex flex-col">
    <div class="px-4 py-3 bg-gray-100 rounded-t flex items-center gap-2">
      <h2 class="text-base font-semibold">{{ title }}</h2>
      <InfoTooltip v-if="tooltip" :text="tooltip" />
    </div>
    <slot />
  </div>
</template>
