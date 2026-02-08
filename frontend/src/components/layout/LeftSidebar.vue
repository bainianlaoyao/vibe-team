<script setup lang="ts">
import { useRoute, RouterLink } from 'vue-router';
import {
  PhHouse,
  PhTray,
  PhChatsCircle,
  PhRobot,
  PhFlowArrow,
  PhFolder,
  PhKey,
  PhChartBar,
  PhGear,
  PhQuestion,
} from '@phosphor-icons/vue';

const route = useRoute();

const navItems = [
  { path: '/', icon: PhHouse, label: 'Dashboard' },
  { path: '/inbox', icon: PhTray, label: 'Inbox' },
  { path: '/chat', icon: PhChatsCircle, label: 'Chat' },
  { path: '/agents', icon: PhRobot, label: 'Agents' },
  { path: '/workflow', icon: PhFlowArrow, label: 'Workflow' },
  { path: '/files', icon: PhFolder, label: 'Files' },
  { path: '/roles', icon: PhKey, label: 'Roles' },
  { path: '/api', icon: PhChartBar, label: 'API' },
];

const isActive = (path: string) => {
  if (path === '/') return route.path === '/';
  return route.path.startsWith(path);
};
</script>

<template>
  <aside class="w-56 bg-bg-tertiary border-r border-border flex flex-col h-screen">
    <!-- Logo -->
    <div class="px-4 py-5 border-b border-border">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-brand flex items-center justify-center">
          <span class="text-white text-sm font-bold">B</span>
        </div>
        <div>
          <div class="text-sm font-semibold text-text-primary">BeeBeeBrain</div>
          <div class="text-xs text-text-tertiary">Agent Manager</div>
        </div>
      </div>
    </div>

    <!-- Project Selector -->
    <div class="px-3 py-3 border-b border-border">
      <div class="px-3 py-2 bg-bg-elevated border border-border rounded-lg">
        <div class="text-xs text-text-tertiary uppercase tracking-wide">Project</div>
        <div class="text-sm font-semibold text-text-primary truncate">
          BeeBeeBrain MVP
        </div>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 overflow-auto px-3 py-3">
      <div class="space-y-1">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          :class="[
            'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
            isActive(item.path)
              ? 'bg-bg-elevated border border-border text-text-primary font-medium shadow-soft'
              : 'text-text-secondary hover:bg-bg-elevated/70 hover:text-text-primary',
          ]"
        >
          <component :is="item.icon" :size="18" />
          <span>{{ item.label }}</span>
        </RouterLink>
      </div>
    </nav>

    <!-- Footer -->
    <div class="px-3 py-3 border-t border-border space-y-1">
      <button
        class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-elevated/70 hover:text-text-primary"
      >
        <PhGear :size="18" />
        <span>Settings</span>
      </button>
      <button
        class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-text-secondary hover:bg-bg-elevated/70 hover:text-text-primary"
      >
        <PhQuestion :size="18" />
        <span>Help</span>
      </button>
    </div>
  </aside>
</template>
