<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<template>
  <div class="border rounded flex flex-col">
    <div class="px-4 py-3 border-b">
      <h2 class="text-base font-semibold">{{ title }}</h2>
    </div>
    <slot />
  </div>
</template>
