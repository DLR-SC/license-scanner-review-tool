<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'default' | 'primary' | 'ghost' | 'text' | 'danger'
    disabled?: boolean
  }>(),
  { variant: 'default', disabled: false },
)
</script>

<template>
  <button
    type="button"
    :disabled="disabled"
    class="cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
    :class="{
      'border rounded py-1 px-3 text-sm hover:bg-gray-200': variant === 'default',
      'border rounded py-1 px-3 text-sm bg-green-50 text-green-700 border-green-300 hover:bg-green-100':
        variant === 'primary',
      'py-1 px-2 text-sm text-gray-400 hover:text-gray-600': variant === 'text',
      'py-1 px-1 text-sm text-gray-400 hover:text-red-500': variant === 'danger',
    }"
  >
    <slot />
  </button>
</template>
