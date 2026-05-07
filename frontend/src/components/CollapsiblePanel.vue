<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { ref } from 'vue'
import CarbonChevronDown from '~icons/carbon/chevron-down'

const open = ref(false)
</script>

<template>
  <div class="border border-gray-200 rounded">
    <div
      class="flex items-center justify-between px-3 py-2 text-sm hover:bg-gray-50 cursor-pointer select-none"
      role="button"
      tabindex="0"
      @click="open = !open"
      @keydown.enter.prevent="open = !open"
      @keydown.space.prevent="open = !open"
    >
      <div class="flex items-center gap-2">
        <slot name="summary" />
      </div>
      <CarbonChevronDown
        class="w-4 h-4 text-gray-400 transition-transform shrink-0"
        :class="open ? 'rotate-180' : ''"
      />
    </div>
    <div v-if="open" class="border-t border-gray-200">
      <slot />
    </div>
  </div>
</template>
