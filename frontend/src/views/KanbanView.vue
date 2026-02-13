<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { PhArrowSquareOut, PhPlus, PhX } from '@phosphor-icons/vue';
import Avatar from '../components/Avatar.vue';
import TaskCard from '../components/TaskCard.vue';
import { useAgentsStore } from '../stores/agents';
import { useTasksStore } from '../stores/tasks';
import { ApiRequestError, api } from '../services/api';
import type { Task, TaskStatus } from '../types';

const tasksStore = useTasksStore();
const agentsStore = useAgentsStore();
const selectedTask = ref<Task | null>(null);
const launchTaskError = ref<string | null>(null);
const launchTaskInfo = ref<string | null>(null);
const launchingTaskId = ref<string | null>(null);

const columns: {
  status: TaskStatus;
  label: string;
  lane: string;
  header: string;
  stripe: string;
  progress: string;
}[] = [
  { status: 'todo', label: 'To do', lane: 'bg-primary-100/70 border-primary-200', header: 'text-text-secondary', stripe: 'border-primary-300', progress: 'bg-primary-400' },
  { status: 'in_progress', label: 'In progress', lane: 'bg-accent-100/60 border-accent-200', header: 'text-accent-700', stripe: 'border-brand', progress: 'bg-brand' },
  { status: 'review', label: 'Review', lane: 'bg-primary-100/60 border-primary-200', header: 'text-warning', stripe: 'border-warning', progress: 'bg-warning' },
  { status: 'done', label: 'Done', lane: 'bg-success/10 border-success/30', header: 'text-success', stripe: 'border-success', progress: 'bg-success' },
  { status: 'blocked', label: 'Blocked', lane: 'bg-error/10 border-error/30', header: 'text-error', stripe: 'border-error', progress: 'bg-error' },
  { status: 'failed', label: 'Failed', lane: 'bg-error/10 border-error/30', header: 'text-error', stripe: 'border-error', progress: 'bg-error' },
  { status: 'canceled', label: 'Canceled', lane: 'bg-primary-200/80 border-primary-300', header: 'text-text-secondary', stripe: 'border-primary-400', progress: 'bg-primary-500' },
];

const getTasksByStatus = (status: TaskStatus) => tasksStore.tasks.filter(task => task.status === status);
const getAgentById = (agentId: string | null) =>
  agentId ? agentsStore.agents.find(agent => agent.id === agentId) : undefined;

const priorityClass = (priority: string) => {
  if (priority === 'high') return 'bg-primary-200 text-text-primary';
  if (priority === 'medium') return 'bg-accent-100 text-accent-700';
  return 'bg-primary-100 text-text-secondary';
};

const totalTasks = computed(() => tasksStore.tasks.length);

const resolveAssigneeApiId = (task: Task): number | null => {
  if (!task.assignedTo) {
    return null;
  }
  const agent = agentsStore.agents.find(item => item.id === task.assignedTo);
  return agent?.apiId ?? null;
};

const buildConversationTitle = (task: Task): string => {
  const taskPrefix = task.apiId ? `Task #${task.apiId}` : task.id;
  return `${taskPrefix}: ${task.title}`;
};

const buildRunPrompt = (task: Task): string => {
  const summary = task.description.trim();
  if (!summary) {
    return `请执行任务：${task.title}`;
  }
  return `请执行任务：${task.title}\n\n任务说明：${summary}`;
};

const buildLaunchTraceId = (taskId: number, conversationId: number): string =>
  `launch-${taskId}-${conversationId}-${Date.now()}`;

const buildLaunchIdempotencyKey = (taskId: number, conversationId: number): string =>
  `launch-${taskId}-${conversationId}-${Date.now()}`;

const launchTaskConversation = async (task: Task) => {
  launchTaskError.value = null;
  launchTaskInfo.value = null;
  if (!task.apiId) {
    launchTaskError.value = 'Missing apiId for selected task.';
    return;
  }
  const assigneeApiId = resolveAssigneeApiId(task);
  if (!assigneeApiId) {
    launchTaskError.value = 'Task must be assigned to an agent before launching a conversation.';
    return;
  }

  launchingTaskId.value = task.id;
  try {
    const existing = await api.listConversations(tasksStore.projectId, assigneeApiId, task.apiId);
    const target =
      existing[0] ??
      (await api.createConversation({
        project_id: tasksStore.projectId,
        agent_id: assigneeApiId,
        task_id: task.apiId,
        title: buildConversationTitle(task),
      }));

    await api.runTask(task.apiId, {
      prompt: buildRunPrompt(task),
      session_id: `conversation-${target.id}`,
      conversation_id: target.id,
      trace_id: buildLaunchTraceId(task.apiId, target.id),
      idempotency_key: buildLaunchIdempotencyKey(task.apiId, target.id),
      actor: 'frontend.launch',
    });

    launchTaskInfo.value = `Task #${task.apiId} launched. Open it from Chat conversation list when needed.`;
    await tasksStore.fetchTasks();
  } catch (cause) {
    const apiError = cause instanceof ApiRequestError ? cause : null;
    launchTaskError.value = apiError
      ? `${apiError.code}: ${apiError.message}`
      : 'Failed to launch task conversation and start task run.';
  } finally {
    launchingTaskId.value = null;
  }
};

onMounted(async () => {
  await Promise.all([tasksStore.fetchTasks(), agentsStore.fetchAgents()]);
});
</script>

<template>
  <div class="flex-1 overflow-hidden">
    <div class="px-4 sm:px-6 lg:px-8 pt-3 flex items-center gap-2 text-sm">
      <button class="px-3 py-1 rounded-full border border-border bg-bg-tertiary text-text-primary">All</button>
      <button class="px-3 py-1 rounded-full border border-border text-text-tertiary hover:text-text-primary">Assigned</button>
      <button class="px-3 py-1 rounded-full border border-border text-text-tertiary hover:text-text-primary">Blocked</button>
      <div class="ml-auto text-text-tertiary">{{ totalTasks }} tasks</div>
    </div>
    <div v-if="launchTaskError" class="px-4 sm:px-6 lg:px-8 pt-2 text-sm text-error">{{ launchTaskError }}</div>
    <div v-if="launchTaskInfo" class="px-4 sm:px-6 lg:px-8 pt-2 text-sm text-success">{{ launchTaskInfo }}</div>

    <div v-if="tasksStore.loading" class="p-6 text-sm text-text-tertiary">Loading tasks...</div>
    <div v-else-if="tasksStore.error" class="p-6 text-sm text-error">{{ tasksStore.error }}</div>
    <div v-else class="h-full flex gap-3 p-4 sm:p-5 lg:p-6 overflow-x-auto">
      <div
        v-for="column in columns"
        :key="column.status"
        :class="['flex-shrink-0 w-64 border rounded-lg p-3', column.lane]"
      >
        <div class="flex items-end justify-between mb-3 min-h-[30px]">
          <h3 :class="['text-base font-semibold leading-tight', column.header]">{{ column.label }}</h3>
          <span class="text-xs font-semibold px-2.5 py-1 rounded-full border border-border bg-bg-elevated text-text-tertiary">
            {{ getTasksByStatus(column.status).length }}
          </span>
        </div>

        <div class="space-y-2 max-h-[calc(100vh-260px)] overflow-y-auto pr-1">
          <TaskCard
            v-for="task in getTasksByStatus(column.status)"
            :key="task.id"
            :task="task"
            :agent="getAgentById(task.assignedTo)"
            :accent-class="column.stripe"
            :progress-class="column.progress"
            avatar-class="w-8 h-8 rounded-full"
            @click="selectedTask = task"
          />
          <div v-if="getTasksByStatus(column.status).length === 0" class="text-center py-10 text-text-tertiary text-sm">
            No tasks
          </div>
        </div>

        <button
          v-if="column.status === 'todo'"
          class="w-full mt-3 flex items-center justify-center gap-2 py-2 text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-bg-elevated rounded-lg transition-all cursor-pointer border border-dashed border-border"
        >
          <PhPlus :size="18" />
          <span>Add Task</span>
        </button>
      </div>
    </div>

    <div
      v-if="selectedTask"
      class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4"
      @click="selectedTask = null"
    >
      <div
        class="bg-bg-elevated rounded-2xl p-8 max-w-2xl w-full max-h-[85vh] overflow-y-auto shadow-strong border border-border"
        @click.stop
      >
        <div class="flex items-start justify-between mb-6">
          <div class="flex-1">
            <div class="flex items-center gap-2 mb-3">
              <span class="text-xs font-mono font-semibold text-text-tertiary">#{{ selectedTask.apiId }}</span>
              <span :class="['text-xs px-3 py-1 rounded-full font-medium uppercase tracking-wide', priorityClass(selectedTask.priority)]">
                {{ selectedTask.priority }}
              </span>
            </div>
            <h2 class="text-xl font-semibold text-text-primary leading-tight">{{ selectedTask.title }}</h2>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="inline-flex items-center gap-1 rounded-md border border-border px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="launchingTaskId === selectedTask.id || !selectedTask.assignedTo"
              @click="launchTaskConversation(selectedTask)"
            >
              <PhArrowSquareOut :size="14" />
              <span>{{ launchingTaskId === selectedTask.id ? 'Launching...' : 'Launch Task' }}</span>
            </button>
            <button
              class="p-2 text-text-tertiary hover:text-text-primary hover:bg-bg-tertiary rounded-lg transition-colors cursor-pointer"
              aria-label="Close task details"
              @click="selectedTask = null"
            >
              <PhX :size="20" />
            </button>
          </div>
        </div>

        <div class="space-y-6">
          <div>
            <h3 class="text-xs font-semibold text-text-primary mb-2 uppercase tracking-wide">Description</h3>
            <p class="text-sm text-text-secondary leading-relaxed">{{ selectedTask.description }}</p>
          </div>

          <div v-if="selectedTask.assignedTo">
            <h3 class="text-xs font-semibold text-text-primary mb-3 uppercase tracking-wide">Assigned To</h3>
            <div class="flex items-center gap-3 p-3 bg-bg-tertiary border border-border rounded-lg">
              <Avatar
                :src="getAgentById(selectedTask.assignedTo)?.avatar"
                :alt="getAgentById(selectedTask.assignedTo)?.name"
                :fallback="getAgentById(selectedTask.assignedTo)?.name?.[0] || 'A'"
                container-class="w-10 h-10 rounded-md"
                text-class="text-base"
              />
              <div>
                <div class="text-sm font-semibold text-text-primary">{{ getAgentById(selectedTask.assignedTo)?.name }}</div>
                <div class="text-xs text-text-tertiary">{{ getAgentById(selectedTask.assignedTo)?.type }}</div>
              </div>
            </div>
          </div>

          <div v-if="selectedTask.status === 'in_progress'">
            <h3 class="text-xs font-semibold text-text-primary mb-3 uppercase tracking-wide">Progress</h3>
            <div class="flex items-center gap-4">
              <div class="flex-1 h-2.5 bg-primary-200 rounded-full overflow-hidden">
                <div class="h-full bg-brand transition-all duration-300" :style="{ width: `${selectedTask.progress}%` }" />
              </div>
              <span class="text-sm font-semibold text-text-primary min-w-[3rem] text-right">{{ selectedTask.progress }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
