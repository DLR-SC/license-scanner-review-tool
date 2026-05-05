<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed, useAttrs } from 'vue'
import parse from 'spdx-expression-parse'
import AppInput from './AppInput.vue'
import CarbonCheckmark from '~icons/carbon/checkmark'
import CarbonWarning from '~icons/carbon/warning'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  allowNone?: boolean
}>()

const model = defineModel<string>()
const attrs = useAttrs()

type Validity = 'valid' | 'invalid' | 'empty'

const validity = computed((): Validity => {
  const value = model.value?.trim()
  if (!value) return 'empty'
  if (props.allowNone && value === 'NONE') return 'valid'
  try {
    parse(value)
    return 'valid'
  } catch {
    return 'invalid'
  }
})
</script>

<template>
  <div class="relative flex items-center font-mono" :class="attrs.class as string">
    <AppInput
      class="w-full pr-7 font-[inherit]"
      :class="{
        'border-green-500': validity === 'valid',
        'border-red-500': validity === 'invalid',
      }"
      v-bind="{ ...attrs, class: undefined }"
      v-model="model"
    />
    <span class="absolute right-2 text-sm leading-none pointer-events-none select-none">
      <CarbonCheckmark v-if="validity === 'valid'" class="text-green-500" />
      <CarbonWarning v-else-if="validity === 'invalid'" class="text-red-500" />
    </span>
  </div>
</template>
