<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import InfoTooltip from '@/components/InfoTooltip.vue'

defineProps<{
  title: string
  tooltip?: string
  headerClass?: string
}>()
</script>

<template>
  <section class="border rounded-lg flex flex-col" :aria-label="title">
    <div class="px-4 py-3 bg-gray-100 rounded-t-lg flex items-center gap-2" :class="headerClass">
      <slot name="icon" />
      <h2 class="text-base font-semibold">{{ title }}</h2>
      <InfoTooltip v-if="tooltip" :text="tooltip" />
    </div>
    <slot />
  </section>
</template>
