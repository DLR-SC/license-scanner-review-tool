<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { useAttrs, useId } from 'vue'

defineOptions({ inheritAttrs: false })

defineProps<{ label: string }>()

const model = defineModel<string>()
const attrs = useAttrs()
const id = useId()
</script>

<template>
  <div class="flex flex-col gap-1" :class="attrs.class as string">
    <label :for="id" class="text-xs text-gray-500 flex items-center gap-1"
      >{{ label }}<slot
    /></label>
    <input
      :id="id"
      class="border rounded px-2 py-1 text-sm"
      v-bind="{ ...attrs, class: undefined }"
      v-model="model"
    />
  </div>
</template>
