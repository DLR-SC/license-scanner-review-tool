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
      'border rounded py-1 px-3 text-sm bg-slate-600 text-white border-slate-700 hover:bg-slate-700':
        variant === 'primary',
      'py-1 px-2 text-sm text-gray-500 hover:text-gray-600': variant === 'text',
      'border rounded py-1 px-3 text-sm text-red-600 border-red-600 hover:bg-red-50':
        variant === 'danger',
    }"
  >
    <slot />
  </button>
</template>
