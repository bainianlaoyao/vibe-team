<script setup lang="ts">
import { computed, onMounted } from 'vue';
import {
  PhDotsThree,
  PhStar,
  PhUsers,
} from '@phosphor-icons/vue';
import { useAgentsStore } from '../../stores/agents';
import { useTasksStore } from '../../stores/tasks';

const agentsStore = useAgentsStore();
const tasksStore = useTasksStore();

const activeAgents = computed(() => agentsStore.agents.filter(a => a.status === 'active').length);
const totalTasks = computed(() => tasksStore.tasks.length);
const completedTasks = computed(() => tasksStore.tasks.filter(t => t.status === 'done').length);
const progressPercent = computed(() =>
  totalTasks.value > 0 ? Math.round((completedTasks.value / totalTasks.value) * 100) : 0
);

onMounted(async () => {
  if (agentsStore.agents.length === 0) {
    await agentsStore.fetchAgents();
  }
  if (tasksStore.tasks.length === 0) {
    await tasksStore.fetchTasks();
  }
});
</script>

<template>
  <div class="bg-bg-elevated border-b border-border px-6 py-4">
    <div class="flex items-start justify-between gap-4">
      <!-- Project Info -->
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-3 mb-2">
          <h1 class="text-xl font-semibold text-text-primary truncate">
            BeeBeeBrain MVP
          </h1>
          <span class="px-2 py-0.5 text-xs font-medium rounded-full bg-success/10 text-success border border-success/20">
            Active
          </span>
        </div>
        <p class="text-sm text-text-secondary line-clamp-1">
          Live project status from backend API.
        </p>
      </div>

      <!-- Actions -->
      <div class="flex items-center gap-2">
        <button
          class="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          aria-label="Favorite"
        >
          <PhStar :size="20" />
        </button>
        <button
          class="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
          aria-label="More options"
        >
          <PhDotsThree :size="20" />
        </button>
      </div>
    </div>

    <!-- Stats -->
    <div class="flex items-center gap-6 mt-4">
      <div class="flex items-center gap-2 text-sm">
        <PhUsers :size="16" class="text-text-tertiary" />
        <span class="text-text-secondary">
          <span class="font-semibold text-text-primary">{{ activeAgents }}</span> active agents
        </span>
      </div>
      <div class="flex items-center gap-2 text-sm">
        <span class="text-text-secondary">
          <span class="font-semibold text-text-primary">{{ completedTasks }}/{{ totalTasks }}</span> tasks done
        </span>
        <div class="w-20 h-1.5 bg-primary-200 rounded-full overflow-hidden">
          <div
            class="h-full bg-success transition-all"
            :style="{ width: `${progressPercent}%` }"
          />
        </div>
        <span class="text-xs text-text-tertiary">{{ progressPercent }}%</span>
      </div>
    </div>
  </div>
</template>
