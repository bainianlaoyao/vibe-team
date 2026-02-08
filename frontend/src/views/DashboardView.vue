<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  PhArrowRight,
  PhCheckCircle,
  PhClock,
  PhFile,
  PhLightning,
  PhWarning,
} from '@phosphor-icons/vue';
import Avatar from '../components/Avatar.vue';
import { api } from '../services/api';
import { useAgentsStore } from '../stores/agents';
import { useFileSystemStore } from '../stores/fileSystem';
import { useTasksStore } from '../stores/tasks';
import type { ProjectUpdate } from '../types';

const agentsStore = useAgentsStore();
const tasksStore = useTasksStore();
const fileStore = useFileSystemStore();
const updates = ref<ProjectUpdate[]>([]);
const loadingUpdates = ref<boolean>(false);
const updatesError = ref<string | null>(null);

const activeAgents = computed(() => agentsStore.agents.filter(a => a.status === 'active'));
const blockedTasks = computed(() =>
  tasksStore.tasks.filter(task => task.status === 'blocked' || task.status === 'failed'),
);
const inProgressTasks = computed(() => tasksStore.tasks.filter(task => task.status === 'in_progress'));
const completedTasks = computed(() => tasksStore.tasks.filter(task => task.status === 'done'));

const docs = computed(() => {
  const root = fileStore.root;
  if (!root) return [];
  const files = root.children.filter(item => item.type === 'file').slice(0, 6);
  return files.map(file => ({
    id: file.id,
    name: file.name,
    updatedAtLabel: file.modifiedAt ? new Date(file.modifiedAt).toLocaleString() : 'Unknown',
  }));
});

const getAgentById = (id: string | null) => (id ? agentsStore.byId[id] : undefined);

onMounted(async () => {
  await Promise.all([agentsStore.fetchAgents(), tasksStore.fetchTasks(), fileStore.fetchTree('.', 2)]);
  loadingUpdates.value = true;
  updatesError.value = null;
  try {
    const rows = await api.listUpdates(tasksStore.projectId);
    updates.value = rows.map(item => ({
      id: item.id,
      summary: item.summary,
      agentId: item.agent_id ? `agent-${item.agent_id}` : null,
      time: new Date(item.created_at).toLocaleString(),
      filesChanged: item.files_changed || [],
    }));
  } catch (error) {
    updatesError.value = error instanceof Error ? error.message : 'Failed to load recent updates.';
  } finally {
    loadingUpdates.value = false;
  }
});
</script>

<template>
  <div class="flex-1 overflow-auto p-6 space-y-6">
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-bg-elevated border border-border rounded-lg p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 rounded-lg bg-success/10">
            <PhLightning :size="20" class="text-success" />
          </div>
          <div>
            <div class="text-2xl font-semibold text-text-primary">{{ activeAgents.length }}</div>
            <div class="text-sm text-text-tertiary">Active Agents</div>
          </div>
        </div>
      </div>
      <div class="bg-bg-elevated border border-border rounded-lg p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 rounded-lg bg-error/10">
            <PhWarning :size="20" class="text-error" />
          </div>
          <div>
            <div class="text-2xl font-semibold text-text-primary">{{ blockedTasks.length }}</div>
            <div class="text-sm text-text-tertiary">Blocked / Failed</div>
          </div>
        </div>
      </div>
      <div class="bg-bg-elevated border border-border rounded-lg p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 rounded-lg bg-accent-100">
            <PhClock :size="20" class="text-accent-700" />
          </div>
          <div>
            <div class="text-2xl font-semibold text-text-primary">{{ inProgressTasks.length }}</div>
            <div class="text-sm text-text-tertiary">In Progress</div>
          </div>
        </div>
      </div>
      <div class="bg-bg-elevated border border-border rounded-lg p-4">
        <div class="flex items-center gap-3">
          <div class="p-2 rounded-lg bg-success/10">
            <PhCheckCircle :size="20" class="text-success" />
          </div>
          <div>
            <div class="text-2xl font-semibold text-text-primary">{{ completedTasks.length }}</div>
            <div class="text-sm text-text-tertiary">Completed</div>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div class="lg:col-span-2 bg-bg-elevated border border-border rounded-lg p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-semibold text-text-primary uppercase tracking-wide">Recent Updates</h3>
        </div>
        <div v-if="loadingUpdates" class="text-sm text-text-tertiary">Loading updates...</div>
        <div v-else-if="updatesError" class="text-sm text-error">{{ updatesError }}</div>
        <div v-else class="space-y-3">
          <div
            v-for="update in updates"
            :key="update.id"
            class="flex items-start gap-3 p-3 bg-bg-tertiary rounded-lg"
          >
            <Avatar
              :src="getAgentById(update.agentId)?.avatar"
              :alt="getAgentById(update.agentId)?.name"
              :fallback="getAgentById(update.agentId)?.name?.[0] || 'A'"
              class="w-8 h-8 rounded-full"
              text-class="text-xs"
            />
            <div class="flex-1 min-w-0">
              <p class="text-sm text-text-primary">{{ update.summary }}</p>
              <div class="flex items-center gap-2 mt-1">
                <span class="text-xs text-text-tertiary">{{ update.time }}</span>
                <span class="text-xs text-text-tertiary">·</span>
                <span class="text-xs text-text-tertiary">{{ update.filesChanged.length }} files</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="bg-bg-elevated border border-border rounded-lg p-5">
        <div class="flex items-center justify-between mb-4">
          <h3 class="text-sm font-semibold text-text-primary uppercase tracking-wide">Project Files</h3>
        </div>
        <div class="space-y-2">
          <div
            v-for="doc in docs"
            :key="doc.id"
            class="flex items-center gap-3 p-2 rounded-lg hover:bg-bg-tertiary"
          >
            <PhFile :size="16" class="text-text-tertiary" />
            <div class="flex-1 min-w-0">
              <div class="text-sm text-text-primary truncate">{{ doc.name }}</div>
              <div class="text-xs text-text-tertiary">{{ doc.updatedAtLabel }}</div>
            </div>
            <PhArrowRight :size="14" class="text-text-tertiary" />
          </div>
        </div>
      </div>
    </div>

    <div class="bg-bg-elevated border border-border rounded-lg p-5">
      <h3 class="text-sm font-semibold text-text-primary uppercase tracking-wide mb-4">Agent Status</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div
          v-for="agent in agentsStore.agents"
          :key="agent.id"
          class="p-4 bg-bg-tertiary rounded-lg border border-border"
        >
          <div class="flex items-center gap-3 mb-3">
            <Avatar
              :src="agent.avatar"
              :alt="agent.name"
              :fallback="agent.name[0]"
              class="w-10 h-10 rounded-full"
              text-class="text-sm"
              :presence="true"
              :presence-status="agent.status"
            />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold text-text-primary truncate">{{ agent.name }}</div>
              <div class="text-xs text-text-tertiary capitalize">{{ agent.status }}</div>
            </div>
          </div>
          <div class="flex items-center gap-2 text-xs text-text-tertiary">
            <span>Health</span>
            <div class="flex-1 h-1.5 bg-primary-200 rounded-full overflow-hidden">
              <div class="h-full bg-brand" :style="{ width: `${agent.health}%` }" />
            </div>
            <span>{{ agent.health }}%</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
