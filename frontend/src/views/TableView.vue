<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { PhArrowSquareOut, PhCaretDown, PhCaretRight, PhGitDiff } from '@phosphor-icons/vue';
import Avatar from '../components/Avatar.vue';
import { useAgentsStore } from '../stores/agents';
import { useTasksStore } from '../stores/tasks';
import type { Agent, RiskFlag, Task, TaskStatus } from '../types';

const agentsStore = useAgentsStore();
const tasksStore = useTasksStore();

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

onMounted(async () => {
  await Promise.all([agentsStore.fetchAgents(), tasksStore.fetchTasks()]);
  expandedAgents.value = new Set([...agentsStore.agents.map(item => item.id), 'unassigned']);
});
</script>

<template>
  <div class="flex-1 overflow-auto p-6">
    <div class="mb-4 flex items-center justify-between">
      <div class="text-sm text-text-tertiary">Agent grouped tasks</div>
      <button class="px-4 py-1.5 text-sm bg-brand hover:bg-brand/90 text-white rounded transition-colors">
        + Add Task
      </button>
    </div>

    <div v-if="tasksStore.loading" class="text-sm text-text-tertiary">Loading tasks...</div>
    <div v-else-if="tasksStore.error" class="text-sm text-error">{{ tasksStore.error }}</div>
    <div v-else class="space-y-6">
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
                    <button class="h-7 w-7 border border-border/70 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-tertiary flex items-center justify-center">
                      <PhGitDiff :size="14" />
                    </button>
                    <button class="h-7 w-7 border border-border/70 rounded-md text-text-secondary hover:text-text-primary hover:bg-bg-tertiary flex items-center justify-center">
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
  </div>
</template>
