<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { RouterView } from 'vue-router'
</script>

<template>
  <header class="leading-none max-h-screen lg:flex lg:items-center border-b justify-between p-1">
    <RouterLink to="/">
      <h1 class="text-xl font-bold text-gray-900 sm:text-2xl">License Scanner Review Tool</h1>
    </RouterLink>
    <RouterLink
      to="/about"
      class="ml-auto text-sm text-gray-500 hover:text-gray-700 transition-colors"
    >
      About
    </RouterLink>
  </header>
  <RouterView />
</template>
