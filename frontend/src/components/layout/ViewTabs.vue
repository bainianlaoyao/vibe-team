<script setup lang="ts">
import { useRoute, RouterLink } from 'vue-router';
import {
  PhTable,
  PhSquaresFour,
  PhSliders,
} from '@phosphor-icons/vue';

const route = useRoute();

const tabs = [
  { path: '/agents/table', icon: PhTable, label: 'Table' },
  { path: '/agents/kanban', icon: PhSquaresFour, label: 'Kanban' },
  { path: '/agents/customize', icon: PhSliders, label: 'Customize' },
];

const isActive = (path: string) => route.path === path;
</script>

<template>
  <div class="bg-bg-elevated border-b border-border px-6">
    <div class="flex items-center gap-1">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.path"
        :to="tab.path"
        :class="[
          'flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 -mb-px transition-colors',
          isActive(tab.path)
            ? 'border-brand text-text-primary'
            : 'border-transparent text-text-secondary hover:text-text-primary hover:border-primary-300',
        ]"
      >
        <component :is="tab.icon" :size="16" />
        <span>{{ tab.label }}</span>
      </RouterLink>
    </div>
  </div>
</template>
