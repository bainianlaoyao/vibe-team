<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { PhArrowSquareOut, PhCaretDown, PhCaretRight, PhGitDiff } from '@phosphor-icons/vue';
import Avatar from '../components/Avatar.vue';
import TaskCreateModal from '../components/TaskCreateModal.vue';
import { useAgentsStore } from '../stores/agents';
import { useTasksStore } from '../stores/tasks';
import { ApiRequestError, api } from '../services/api';
import type { Agent, RiskFlag, Task, TaskStatus } from '../types';

const agentsStore = useAgentsStore();
const tasksStore = useTasksStore();
const createModalOpen = ref<boolean>(false);
const creatingTask = ref<boolean>(false);
const createTaskError = ref<string | null>(null);
const launchTaskError = ref<string | null>(null);
const launchTaskInfo = ref<string | null>(null);
const launchingTaskId = ref<string | null>(null);

const statusMeta: Record<TaskStatus, { label: string; dot: string; text: string }> = {
  todo: { label: 'To do', dot: 'bg-primary-300 shadow-[0_0_0_4px_rgba(154,152,146,0.15)]', text: 'text-text-tertiary' },
  in_progress: { label: 'In progress', dot: 'bg-brand shadow-[0_0_0_4px_rgba(47,65,86,0.15)]', text: 'text-accent-700' },
  review: { label: 'Review', dot: 'bg-accent-500 shadow-[0_0_0_4px_rgba(74,127,224,0.16)]', text: 'text-accent-700' },
  done: { label: 'Done', dot: 'bg-success shadow-[0_0_0_4px_rgba(47,125,75,0.15)]', text: 'text-success' },
  blocked: { label: 'Blocked', dot: 'bg-error shadow-[0_0_0_4px_rgba(193,70,63,0.12)]', text: 'text-error' },
  failed: { label: 'Failed', dot: 'bg-error shadow-[0_0_0_4px_rgba(193,70,63,0.12)]', text: 'text-error' },
  canceled: { label: 'Canceled', dot: 'bg-primary-400 shadow-[0_0_0_4px_rgba(154,152,146,0.2)]', text: 'text-text-secondary' },
};

const expandedAgents = ref<Set<string>>(new Set());

const toggleAgent = (agentId: string) => {
  const next = new Set(expandedAgents.value);
  if (next.has(agentId)) next.delete(agentId);
  else next.add(agentId);
  expandedAgents.value = next;
};

const getTasksByAgent = (agentId: string | null) =>
  tasksStore.tasks.filter(task => task.assignedTo === agentId);

const getBotName = (agent: Agent | null, agentTasks: Task[]) => {
  if (!agent) return 'Unassigned';
  const capabilityText = agent.capabilities.join(' ').toLowerCase();
  const taskText = agentTasks.map(task => task.title).join(' ').toLowerCase();
  if (capabilityText.includes('ui') || capabilityText.includes('frontend') || taskText.includes('design')) return 'Design Agent';
  if (capabilityText.includes('api') || capabilityText.includes('backend') || taskText.includes('api')) return 'API Agent';
  if (capabilityText.includes('testing') || taskText.includes('test')) return 'QA Agent';
  if (capabilityText.includes('database') || taskText.includes('schema')) return 'Data Architect';
  return 'Generalist Agent';
};

const getAgentWorkingState = (flags: RiskFlag[]) => {
  if (flags.includes('failing')) return { label: 'Stuck in debug', style: 'bg-primary-200 text-error' };
  if (flags.includes('stuck') || flags.includes('needs_review')) return { label: 'Needs attention', style: 'bg-accent-100 text-accent-700' };
  return { label: 'Working fine!', style: 'bg-primary-100 text-success' };
};

const agentSections = computed(() => {
  const sections = agentsStore.agents.map(agent => {
    const agentTasks = getTasksByAgent(agent.id);
    const agentRisks = [...new Set(agentTasks.flatMap(task => task.riskFlags || []))];
    const todoCount = agentTasks.filter(task => task.status === 'todo').length;
    return {
      agent,
      agentId: agent.id,
      agentTasks,
      displayName: getBotName(agent, agentTasks),
      workingState: getAgentWorkingState(agentRisks),
      todoPercent: agentTasks.length === 0 ? 0 : Math.round((todoCount / agentTasks.length) * 100),
    };
  });
  const unassignedTasks = getTasksByAgent(null);
  sections.push({
    agent: null as unknown as Agent,
    agentId: 'unassigned',
    agentTasks: unassignedTasks,
    displayName: 'Unassigned',
    workingState: { label: 'Pending assignment', style: 'bg-primary-100 text-text-secondary' },
    todoPercent: 100,
  });
  return sections;
});

const openCreateModal = () => {
  createTaskError.value = null;
  createModalOpen.value = true;
};

const closeCreateModal = () => {
  createModalOpen.value = false;
};

const resolveAssigneeApiId = (task: Task): number | null => {
  if (!task.assignedTo) {
    return null;
  }
  return agentsStore.byId[task.assignedTo]?.apiId ?? null;
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

const handleCreateTask = async (payload: {
  title: string;
  description: string;
  assigneeApiId: number | null;
  priority: 'high' | 'medium' | 'low';
}) => {
  creatingTask.value = true;
  createTaskError.value = null;
  await tasksStore.createTask({
    title: payload.title,
    description: payload.description,
    assigneeApiId: payload.assigneeApiId,
    priority: payload.priority,
  });
  if (tasksStore.error) {
    createTaskError.value = tasksStore.error;
  } else {
    createModalOpen.value = false;
  }
  creatingTask.value = false;
};

onMounted(async () => {
  await Promise.all([agentsStore.fetchAgents(), tasksStore.fetchTasks()]);
  expandedAgents.value = new Set([...agentsStore.agents.map(item => item.id), 'unassigned']);
});
</script>

<template>
  <div class="flex-1 overflow-auto p-6">
    <div class="mb-4 flex items-center justify-between">
      <div class="text-sm text-text-tertiary">Agent grouped tasks</div>
      <button
        class="px-4 py-1.5 text-sm bg-brand hover:bg-brand/90 text-white rounded transition-colors"
        @click="openCreateModal"
      >
        + Add Task
      </button>
    </div>

    <div v-if="tasksStore.loading" class="text-sm text-text-tertiary">Loading tasks...</div>
    <div v-else-if="tasksStore.error" class="text-sm text-error">{{ tasksStore.error }}</div>
    <div v-else class="space-y-6">
      <div v-if="launchTaskError" class="text-sm text-error">{{ launchTaskError }}</div>
      <div v-if="launchTaskInfo" class="text-sm text-success">{{ launchTaskInfo }}</div>
      <div v-for="section in agentSections" :key="section.agentId" class="mb-6">
        <div class="flex items-center justify-between bg-bg-elevated px-4 py-1.5 rounded-t-lg border border-border">
          <button class="flex items-center gap-3 flex-1 text-left" @click="toggleAgent(section.agentId)">
            <PhCaretDown v-if="expandedAgents.has(section.agentId)" :size="16" />
            <PhCaretRight v-else :size="16" />
            <Avatar
              :src="section.agent?.avatar"
              :alt="section.agent?.name"
              fallback="U"
              container-class="w-8 h-8 rounded-full"
              text-class="text-base"
            />
            <div>
              <div class="text-sm font-semibold text-text-primary">{{ section.displayName }}</div>
              <div class="text-sm text-text-tertiary">
                {{ section.agent ? `Focus: ${section.agent.capabilities.slice(0, 3).join(', ')}` : 'Unassigned' }}
                · {{ section.agentTasks.length }} tasks · Todo {{ section.todoPercent }}%
              </div>
            </div>
          </button>
          <div class="hidden md:flex items-center gap-2">
            <span :class="['text-sm px-2 py-0.5 rounded-full border border-border', section.workingState.style]">
              {{ section.workingState.label }}
            </span>
          </div>
        </div>

        <div v-if="expandedAgents.has(section.agentId)" class="border border-t-0 border-border rounded-b-lg overflow-hidden">
          <table class="w-full text-sm">
            <thead class="border-b border-border/70">
              <tr class="text-left text-xs text-text-tertiary uppercase tracking-wide">
                <th class="w-32 px-4 py-1.5">Status</th>
                <th class="px-4 py-1.5">Task</th>
                <th class="px-4 py-1.5 w-52">Files changed</th>
                <th class="px-4 py-1.5 w-36">Actions</th>
              </tr>
            </thead>
            <tbody class="bg-bg-elevated">
              <tr
                v-for="task in section.agentTasks"
                :key="task.id"
                :class="[
                  'border-t border-border/70 hover:bg-bg-tertiary/40 transition-colors',
                  task.status === 'blocked' || task.status === 'failed' ? 'border-l-2 border-error/70 bg-error/5' : '',
                ]"
              >
                <td class="px-4 py-2.5 align-middle">
                  <div class="flex items-center gap-2">
                    <span :class="['inline-block w-2.5 h-2.5 rounded-full', statusMeta[task.status].dot]" />
                    <span :class="['text-[11px] uppercase tracking-wide whitespace-nowrap', statusMeta[task.status].text]">
                      {{ statusMeta[task.status].label }}
                    </span>
                  </div>
                </td>
                <td class="px-4 py-2.5 align-middle">
                  <div class="flex items-start gap-2">
                    <span class="text-xs font-mono text-text-tertiary">#{{ task.apiId }}</span>
                    <div class="text-sm font-medium text-text-primary line-clamp-1">
                      {{ task.title }} <span class="text-text-tertiary font-normal">— {{ task.description }}</span>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-2.5 align-middle">
                  <div class="text-xs text-text-tertiary">
                    {{ task.changedFiles.length > 0 ? `${task.changedFiles.length} files` : '—' }}
                  </div>
                </td>
                <td class="px-4 py-2.5 align-middle">
                  <div class="flex items-center gap-2">
                    <button
                      class="h-7 w-7 border border-border/70 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-tertiary flex items-center justify-center"
                      aria-label="View task diff"
                    >
                      <PhGitDiff :size="14" />
                    </button>
                    <button
                      class="h-7 w-7 border border-border/70 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-tertiary flex items-center justify-center"
                      aria-label="Launch task"
                      :disabled="launchingTaskId === task.id || !task.assignedTo"
                      @click="launchTaskConversation(task)"
                    >
                      <PhArrowSquareOut :size="14" />
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
    <TaskCreateModal
      :open="createModalOpen"
      :agents="agentsStore.agents"
      :submitting="creatingTask"
      :error="createTaskError || tasksStore.error"
      @close="closeCreateModal"
      @submit="handleCreateTask"
    />
  </div>
</template>
