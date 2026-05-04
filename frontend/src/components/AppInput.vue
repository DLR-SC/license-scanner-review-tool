<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
const model = defineModel<string>()
</script>

<template>
  <input class="border rounded px-2 py-1 text-sm" v-model="model" />
</template>
