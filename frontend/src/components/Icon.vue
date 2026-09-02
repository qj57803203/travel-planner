<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 18 })

// 统一线性图标（Lucide 风格，1.6 描边），保证全站图标视觉一致
const ICONS: Record<string, string> = {
  compass:
    '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
  sparkles:
    '<path d="M12 3c.6 4.4 3.6 7.4 8 8-4.4.6-7.4 3.6-8 8-.6-4.4-3.6-7.4-8-8 4.4-.6 7.4-3.6 8-8z"/><path d="M18.5 2.5v3"/><path d="M20 4h-3"/>',
  refresh:
    '<path d="M3 12a9 9 0 0 1 15.5-6.2L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-15.5 6.2L3 16"/><path d="M3 21v-5h5"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2.5"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  bed: '<path d="M2 20v-7a1.5 1.5 0 0 1 1.5-1.5h17A1.5 1.5 0 0 1 22 13v7"/><path d="M2 20h20"/><path d="M4 11V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v5"/>',
  pin: '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
  utensils:
    '<path d="M5 2v7a3 3 0 0 0 3 3v10"/><path d="M5 2v7"/><path d="M8 2v7"/><path d="M17 2v20"/><path d="M17 2c-2.2 0-3 1.8-3 4 0 2 1 3.5 3 3.5s3-1.5 3-3.5c0-2.2-.8-4-3-4z"/>',
  train:
    '<rect x="4" y="3" width="16" height="13" rx="2.5"/><path d="M4 11h16"/><path d="M9 19.5 7 22"/><path d="M15 19.5 17 22"/><path d="M8 7h.01"/><path d="M16 7h.01"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  calendar:
    '<rect x="3" y="5" width="18" height="16" rx="2.5"/><path d="M16 3v4"/><path d="M8 3v4"/><path d="M3 11h18"/>',
  arrow: '<path d="M5 12h14"/><path d="m13 6 6 6-6 6"/>',
  map: '<path d="M9 3 3 6v15l6-3 6 3 6-3V3l-6 3-6-3z"/><path d="M9 3v15"/><path d="M15 6v15"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.9 4.9 1.4 1.4"/><path d="m17.7 17.7 1.4 1.4"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.3 17.7-1.4 1.4"/><path d="m19.1 4.9-1.4 1.4"/>',
  book: '<path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>',
  check: '<path d="M20 6 9 17l-5-5"/>',
}

const inner = computed(() => ICONS[props.name] ?? ICONS.compass)
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    v-html="inner"
  />
</template>
