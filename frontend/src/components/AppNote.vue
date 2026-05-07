<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
withDefaults(defineProps<{ variant?: 'info' | 'warning' | 'success' }>(), { variant: 'info' })
</script>

<template>
  <div
    class="text-sm rounded px-3 py-2 border flex gap-2"
    :class="{
      'bg-blue-50 border-blue-200 text-blue-800': variant === 'info',
      'bg-amber-50 border-amber-200 text-amber-800': variant === 'warning',
      'bg-green-50 border-green-200 text-green-800': variant === 'success',
    }"
  >
    <slot />
  </div>
</template>
