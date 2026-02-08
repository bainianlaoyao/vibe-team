import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { ApiRequestError, api, type BackendTask } from '../services/api';
import type { DashboardStats, Task, TaskPriority, TaskStatus } from '../types';

function mapTaskStatus(status: string): TaskStatus {
  switch (status) {
    case 'running':
      return 'in_progress';
    case 'review':
      return 'review';
    case 'done':
      return 'done';
    case 'blocked':
      return 'blocked';
    case 'failed':
      return 'failed';
    case 'cancelled':
      return 'canceled';
    default:
      return 'todo';
  }
}

function toBackendStatus(status: TaskStatus): string {
  switch (status) {
    case 'in_progress':
      return 'running';
    case 'canceled':
      return 'cancelled';
    default:
      return status;
  }
}

function mapTaskPriority(priority: number): TaskPriority {
  if (priority <= 2) return 'high';
  if (priority <= 3) return 'medium';
  return 'low';
}

function toBackendPriority(priority: TaskPriority): number {
  if (priority === 'high') return 1;
  if (priority === 'low') return 5;
  return 3;
}

function statusProgress(status: TaskStatus): number {
  if (status === 'done') return 100;
  if (status === 'review') return 90;
  if (status === 'in_progress') return 60;
  return 0;
}

function toUiTask(row: BackendTask): Task {
  const status = mapTaskStatus(row.status);
  const riskFlags: Task['riskFlags'] = [];
  if (status === 'blocked') riskFlags.push('stuck');
  if (status === 'failed') riskFlags.push('failing');
  if (status === 'review') riskFlags.push('needs_review');
  return {
    id: `task-${row.id}`,
    apiId: row.id,
    title: row.title,
    description: row.description || '',
    status,
    priority: mapTaskPriority(row.priority),
    assignedTo: row.assignee_agent_id ? `agent-${row.assignee_agent_id}` : null,
    dependencies: row.parent_task_id ? [`task-${row.parent_task_id}`] : [],
    blocks: [],
    progress: statusProgress(status),
    riskFlags,
    changedFiles: [],
    diffAdd: 0,
    diffDel: 0,
    createdAt: new Date(row.created_at),
    updatedAt: new Date(row.updated_at),
  };
}

export const useTasksStore = defineStore('tasks', () => {
  const projectId = ref<number>(api.getProjectId());
  const tasks = ref<Task[]>([]);
  const stats = ref<DashboardStats | null>(null);
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  const byApiId = computed<Record<number, Task>>(() =>
    Object.fromEntries(tasks.value.map(task => [task.apiId, task])),
  );

  async function fetchTasks(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const rows = await api.listTasks(projectId.value);
      tasks.value = rows.map(toUiTask);
      const statsRow = await api.getTaskStats(projectId.value);
      stats.value = statsRow;
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to load tasks.';
    } finally {
      loading.value = false;
    }
  }

  async function createTask(input: {
    title: string;
    description?: string;
    assigneeApiId?: number | null;
    priority?: TaskPriority;
  }): Promise<void> {
    try {
      await api.createTask({
        project_id: projectId.value,
        title: input.title,
        description: input.description || '',
        assignee_agent_id: input.assigneeApiId ?? null,
        priority: toBackendPriority(input.priority || 'medium'),
      });
      await fetchTasks();
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to create task.';
    }
  }

  async function updateTaskStatus(task: Task, status: TaskStatus): Promise<void> {
    if (!task.apiId) {
      error.value = 'Missing apiId for selected task.';
      return;
    }
    try {
      await api.updateTask(task.apiId, { status: toBackendStatus(status) });
      await fetchTasks();
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to update task status.';
    }
  }

  async function commandTask(task: Task, command: 'pause' | 'resume' | 'retry' | 'cancel'): Promise<void> {
    if (!task.apiId) {
      error.value = 'Missing apiId for selected task.';
      return;
    }
    try {
      await api.commandTask(task.apiId, command);
      await fetchTasks();
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to execute task command.';
    }
  }

  return {
    projectId,
    tasks,
    stats,
    byApiId,
    loading,
    error,
    fetchTasks,
    createTask,
    updateTaskStatus,
    commandTask,
  };
});
