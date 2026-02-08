<script setup lang="ts">
import { computed } from 'vue';
import type { Task, Agent } from '../types';
import Avatar from './Avatar.vue';

const props = defineProps<{
  task: Task;
  agent?: Agent;
  accentClass?: string;
  progressClass?: string;
  avatarClass?: string;
}>();

const emit = defineEmits<{
  click: [task: Task];
}>();

const priorityClass = computed(() => {
  switch (props.task.priority) {
    case 'high':
      return 'bg-primary-200 text-text-primary';
    case 'medium':
      return 'bg-accent-100 text-accent-700';
    default:
      return 'bg-primary-100 text-text-secondary';
  }
});

const taskNumber = computed(() => props.task.id.split('-')[1]);
</script>

<template>
  <div
    class="bg-bg-elevated border-l-2 rounded-lg p-3 shadow-soft cursor-pointer hover:shadow-medium transition-shadow"
    :class="accentClass"
    @click="emit('click', task)"
  >
    <div class="flex items-start justify-between gap-2 mb-2">
      <span class="text-xs font-mono text-text-tertiary">#{{ taskNumber }}</span>
      <span
        class="text-xs px-2 py-0.5 rounded-full font-medium uppercase tracking-wide"
        :class="priorityClass"
      >
        {{ task.priority }}
      </span>
    </div>

    <h4 class="text-sm font-semibold text-text-primary mb-1 line-clamp-2">
      {{ task.title }}
    </h4>

    <p class="text-xs text-text-tertiary line-clamp-2 mb-3">
      {{ task.description }}
    </p>

    <div v-if="task.status === 'in_progress'" class="mb-3">
      <div class="flex items-center justify-between text-xs text-text-tertiary mb-1">
        <span>Progress</span>
        <span>{{ task.progress }}%</span>
      </div>
      <div class="w-full h-1.5 bg-primary-200 rounded-full overflow-hidden">
        <div
          class="h-full transition-all"
          :class="progressClass"
          :style="{ width: `${task.progress}%` }"
        />
      </div>
    </div>

    <div class="flex items-center justify-between">
      <div v-if="agent" class="flex items-center gap-2">
        <Avatar
          :src="agent.avatar"
          :alt="agent.name"
          :fallback="agent.name[0]"
          :container-class="avatarClass"
          text-class="text-xs"
          :presence="true"
          :presence-status="agent.status"
        />
        <span class="text-xs text-text-secondary">{{ agent.name }}</span>
      </div>
      <div v-else class="text-xs text-text-tertiary">Unassigned</div>

      <div v-if="task.changedFiles.length > 0" class="text-xs text-text-tertiary">
        {{ task.changedFiles.length }} files
      </div>
    </div>
  </div>
</template>
