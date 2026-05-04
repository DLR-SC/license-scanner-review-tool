<!--
SPDX-FileCopyrightText: 2026 Lukas Hass <lukas@slucky.de>

SPDX-License-Identifier: Apache-2.0
-->

<template>
  <div class="border rounded flex flex-col">
    <div class="px-3 py-2 border-b">
      <slot name="title"> </slot>
    </div>
    <slot />
  </div>
</template>
