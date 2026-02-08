<script setup lang="ts">
import { computed, reactive, watch } from 'vue';
import { PhX } from '@phosphor-icons/vue';
import type { Agent, TaskPriority } from '../types';

const props = withDefaults(
  defineProps<{
    open: boolean;
    agents: Agent[];
    submitting?: boolean;
    error?: string | null;
  }>(),
  {
    submitting: false,
    error: null,
  },
);

const emit = defineEmits<{
  close: [];
  submit: [
    {
      title: string;
      description: string;
      assigneeApiId: number | null;
      priority: TaskPriority;
    },
  ];
}>();

const form = reactive({
  title: '',
  description: '',
  assignee: '',
  priority: 'medium' as TaskPriority,
});

const validationError = computed(() =>
  form.title.trim() ? null : 'Task title is required.',
);

watch(
  () => props.open,
  (isOpen) => {
    if (!isOpen) return;
    form.title = '';
    form.description = '';
    form.assignee = '';
    form.priority = 'medium';
  },
);

const submit = () => {
  if (validationError.value) return;
  const assigneeApiId = form.assignee ? Number(form.assignee) : null;
  emit('submit', {
    title: form.title.trim(),
    description: form.description.trim(),
    assigneeApiId,
    priority: form.priority,
  });
};
</script>

<template>
  <div
    v-if="open"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
    @click="emit('close')"
  >
    <div
      class="w-full max-w-lg rounded-xl border border-border bg-bg-elevated p-5 shadow-strong"
      @click.stop
    >
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-base font-semibold text-text-primary">Create task</h2>
        <button
          type="button"
          class="rounded-md border border-border bg-bg-tertiary p-2 text-text-secondary hover:text-text-primary"
          aria-label="Close create task modal"
          @click="emit('close')"
        >
          <PhX :size="14" />
        </button>
      </div>

      <form class="space-y-4" @submit.prevent="submit">
        <div class="space-y-1">
          <label for="task-create-title" class="text-xs uppercase tracking-wide text-text-tertiary">Title</label>
          <input
            id="task-create-title"
            v-model="form.title"
            name="title"
            class="w-full rounded-md border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
            placeholder="Task title"
          />
        </div>

        <div class="space-y-1">
          <label for="task-create-description" class="text-xs uppercase tracking-wide text-text-tertiary">Description</label>
          <textarea
            id="task-create-description"
            v-model="form.description"
            name="description"
            rows="4"
            class="w-full rounded-md border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
            placeholder="Describe expected output"
          />
        </div>

        <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div class="space-y-1">
            <label for="task-create-assignee" class="text-xs uppercase tracking-wide text-text-tertiary">Assign Agent</label>
            <select
              id="task-create-assignee"
              v-model="form.assignee"
              name="assignee_agent_id"
              class="w-full rounded-md border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
            >
              <option value="">Unassigned</option>
              <option
                v-for="agent in agents"
                :key="agent.id"
                :value="agent.apiId"
              >
                {{ agent.name }}
              </option>
            </select>
          </div>

          <div class="space-y-1">
            <label for="task-create-priority" class="text-xs uppercase tracking-wide text-text-tertiary">Priority</label>
            <select
              id="task-create-priority"
              v-model="form.priority"
              name="priority"
              class="w-full rounded-md border border-border bg-bg-tertiary px-3 py-2 text-sm text-text-primary"
            >
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </div>
        </div>

        <p v-if="validationError" class="text-xs text-error">{{ validationError }}</p>
        <p v-else-if="error" class="text-xs text-error">{{ error }}</p>

        <button
          type="submit"
          class="w-full rounded-md bg-brand px-4 py-2 text-sm text-white disabled:opacity-60"
          :disabled="Boolean(validationError) || submitting"
        >
          {{ submitting ? 'Creating...' : 'Create Task' }}
        </button>
      </form>
    </div>
  </div>
</template>
