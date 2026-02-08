import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import type { Agent, AgentStatus, AgentType } from '../types';
import { ApiRequestError, api } from '../services/api';

function mapProviderToAgentType(provider: string): AgentType {
  if (provider.includes('claude')) return 'claude';
  if (provider.includes('gemini')) return 'gemini';
  if (provider.includes('codex')) return 'codex';
  if (provider.includes('cursor')) return 'cursor';
  return 'custom';
}

function mapAgentStatus(status: string): AgentStatus {
  if (status === 'active') return 'active';
  if (status === 'inactive') return 'idle';
  return 'idle';
}

function avatarByIndex(index: number): string {
  const id = (index % 5) + 1;
  return `/avatars/agent-${id}.png`;
}

export const useAgentsStore = defineStore('agents', () => {
  const projectId = ref<number>(api.getProjectId());
  const agents = ref<Agent[]>([]);
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  const byId = computed<Record<string, Agent>>(() =>
    Object.fromEntries(agents.value.map(agent => [agent.id, agent])),
  );

  async function fetchAgents(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const rows = await api.listAgents(projectId.value);
      const healthRows = await Promise.all(rows.map(row => api.getAgentHealth(row.id)));
      const healthMap = new Map<number, number>(healthRows.map(item => [item.agent_id, item.health]));
      agents.value = rows.map((row, index) => ({
        id: `agent-${row.id}`,
        apiId: row.id,
        name: row.name,
        type: mapProviderToAgentType(row.model_provider),
        avatar: avatarByIndex(index),
        status: mapAgentStatus(row.status),
        health: healthMap.get(row.id) ?? 0,
        capabilities: row.enabled_tools_json,
        currentTasks: [],
      }));
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to load agents.';
    } finally {
      loading.value = false;
    }
  }

  async function updateAgent(agent: Agent): Promise<void> {
    if (!agent.apiId) {
      error.value = 'Missing apiId for selected agent.';
      return;
    }
    try {
      await api.updateAgent(agent.apiId, {
        name: agent.name,
      });
      await fetchAgents();
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to update agent.';
    }
  }

  return {
    projectId,
    agents,
    byId,
    loading,
    error,
    fetchAgents,
    updateAgent,
  };
});
