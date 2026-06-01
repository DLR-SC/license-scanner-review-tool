<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { computed, useAttrs, useId } from 'vue'
import parse from 'spdx-expression-parse'
import CarbonCheckmark from '~icons/carbon/checkmark'
import CarbonWarning from '~icons/carbon/warning'
import InfoTooltip from './InfoTooltip.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  label: string
  allowNone?: boolean
}>()

const model = defineModel<string>()
const attrs = useAttrs()
const id = useId()

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
  <div class="flex flex-col gap-1" :class="attrs.class as string">
    <label :for="id" class="text-xs text-gray-500 flex items-center gap-1"
      >{{ label }}<slot
    /></label>
    <div class="relative flex items-center">
      <input
        :id="id"
        class="w-full border rounded px-2 py-1 pr-7 text-sm font-mono"
        :class="{
          'border-green-500': validity === 'valid',
          'border-red-500': validity === 'invalid',
        }"
        v-bind="{ ...attrs, class: undefined }"
        v-model="model"
      />
      <span class="absolute right-2 text-sm leading-none select-none flex items-center gap-1">
        <CarbonCheckmark v-if="validity === 'valid'" class="text-green-500 pointer-events-none" />
        <InfoTooltip v-else-if="validity === 'invalid'">
          <template #icon>
            <CarbonWarning class="text-red-500" aria-hidden="true" />
          </template>
          Not a valid
          <a
            href="https://spdx.github.io/spdx-spec/v2.3/SPDX-license-expressions/"
            target="_blank"
            rel="noopener noreferrer"
            class="underline"
            >SPDX expression</a
          >.
        </InfoTooltip>
      </span>
    </div>
  </div>
</template>
