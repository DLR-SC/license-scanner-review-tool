<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <header class="leading-none max-h-screen lg:flex lg:items-center border-b p-1">
    <h1 class="text-xl font-bold text-gray-900 sm:text-2xl">License Scanner Review Tool</h1>
  </header>
  <RouterView />
</template>
