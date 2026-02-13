import type {
  ConversationSummary,
  FileNode,
  PermissionLevel,
  RoleProfile,
  UsageBudget,
  UsageError,
  UsageTimelinePoint,
} from '../types';

const DEFAULT_BASE_URL = 'http://127.0.0.1:8000/api/v1';
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || DEFAULT_BASE_URL).replace(/\/+$/, '');
const DEFAULT_PROJECT_ID = Number(import.meta.env.VITE_PROJECT_ID || '1');
const STATIC_API_TOKEN = import.meta.env.VITE_API_TOKEN || '';

export class ApiRequestError extends Error {
  public readonly status: number;
  public readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

export interface BackendAgent {
  id: number;
  project_id: number;
  name: string;
  role: string;
  model_provider: string;
  model_name: string;
  enabled_tools_json: string[];
  status: string;
}

export interface BackendAgentHealth {
  agent_id: number;
  health: number;
  state: string;
  active_task_count: number;
  blocked_task_count: number;
  failed_task_count: number;
  done_task_count: number;
  active_run_count: number;
}

export interface BackendTask {
  id: number;
  project_id: number;
  title: string;
  description: string | null;
  status: string;
  priority: number;
  assignee_agent_id: number | null;
  parent_task_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface BackendTaskRun {
  id: number;
  task_id: number;
  agent_id: number | null;
  run_status: string;
  attempt: number;
  idempotency_key: string;
  started_at: string;
  ended_at: string | null;
  next_retry_at: string | null;
  error_code: string | null;
  error_message: string | null;
  token_in: number;
  token_out: number;
  cost_usd: string;
  version: number;
}

export interface BackendTaskStats {
  total: number;
  todo: number;
  running: number;
  review: number;
  done: number;
  blocked: number;
  failed: number;
  cancelled: number;
}

export interface BackendProjectUpdate {
  id: string;
  summary: string;
  task_id: number | null;
  run_id: number | null;
  agent_id: number | null;
  created_at: string;
  files_changed: string[];
}

export interface BackendInboxItem {
  id: number;
  project_id: number;
  source_type: string;
  source_id: string;
  item_type: string;
  title: string;
  content: string;
  status: 'open' | 'closed';
  created_at: string;
  resolved_at: string | null;
  resolver: string | null;
  version: number;
  is_read: boolean;
}

interface BackendConversationItem {
  id: number;
  title: string;
  status: string;
  agent_id: number;
  task_id: number | null;
  updated_at: string;
}

interface BackendConversationList {
  items: BackendConversationItem[];
}

interface BackendUsageBudget {
  month: string;
  budget_usd: string;
  used_usd: string;
  remaining_usd: string;
  utilization_ratio: number;
}

interface BackendUsageTimelinePoint {
  date: string;
  total_request_count: number;
  providers: Record<string, { request_count: number; cost_usd: string }>;
}

interface BackendUsageError {
  timestamp: string;
  model_id: string | null;
  error_type: string;
  message: string;
}

interface BackendFilesTree {
  root: BackendFileNode;
}

interface BackendFileNode {
  id: string;
  name: string;
  path: string;
  type: 'file' | 'folder';
  kind: string;
  size_bytes: number | null;
  modified_at: string | null;
  owner: string;
  permission: PermissionLevel;
  children: BackendFileNode[];
}

interface BackendFileContent {
  id: string;
  path: string;
  name: string;
  permission: PermissionLevel;
  content_type: string;
  content: string | null;
}

interface BackendRole {
  id: string;
  name: string;
  description: string;
  checkpoint_preference: string;
  tags: string[];
}

function resolveToken(): string {
  const storageToken =
    typeof window !== 'undefined' ? window.localStorage.getItem('BBB_API_TOKEN') || '' : '';
  return storageToken || STATIC_API_TOKEN;
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) {
      search.set(key, String(value));
    }
  }
  const serialized = search.toString();
  return serialized ? `?${serialized}` : '';
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json');
  }
  const token = resolveToken();
  if (token) {
    headers.set('X-API-Key', token);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) {
    const fallbackMessage = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { error?: { code?: string; message?: string } };
      throw new ApiRequestError(
        response.status,
        payload.error?.code || 'REQUEST_FAILED',
        payload.error?.message || fallbackMessage,
      );
    } catch (error) {
      if (error instanceof ApiRequestError) {
        throw error;
      }
      throw new ApiRequestError(response.status, 'REQUEST_FAILED', fallbackMessage);
    }
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function toFileNode(input: BackendFileNode): FileNode {
  return {
    id: input.id,
    name: input.name,
    path: input.path,
    type: input.type,
    kind: input.kind,
    sizeBytes: input.size_bytes,
    modifiedAt: input.modified_at,
    owner: input.owner,
    permission: input.permission,
    children: input.children.map(toFileNode),
  };
}

export const api = {
  getProjectId(): number {
    return DEFAULT_PROJECT_ID;
  },

  listAgents(projectId = DEFAULT_PROJECT_ID): Promise<BackendAgent[]> {
    return request<BackendAgent[]>(`/agents${buildQuery({ project_id: projectId })}`);
  },

  updateAgent(agentId: number, payload: Partial<BackendAgent>): Promise<BackendAgent> {
    return request<BackendAgent>(`/agents/${agentId}`, { method: 'PATCH', body: payload });
  },

  getAgentHealth(agentId: number): Promise<BackendAgentHealth> {
    return request<BackendAgentHealth>(`/agents/${agentId}/health`);
  },

  listTasks(projectId = DEFAULT_PROJECT_ID): Promise<BackendTask[]> {
    return request<BackendTask[]>(`/tasks${buildQuery({ project_id: projectId })}`);
  },

  createTask(payload: {
    project_id: number;
    title: string;
    description?: string;
    assignee_agent_id?: number | null;
    priority?: number;
  }): Promise<BackendTask> {
    return request<BackendTask>('/tasks', { method: 'POST', body: payload });
  },

  updateTask(taskId: number, payload: Partial<BackendTask>): Promise<BackendTask> {
    return request<BackendTask>(`/tasks/${taskId}`, { method: 'PATCH', body: payload });
  },

  commandTask(taskId: number, command: 'pause' | 'resume' | 'retry' | 'cancel'): Promise<BackendTask> {
    return request<BackendTask>(`/tasks/${taskId}/${command}`, {
      method: 'POST',
      body: {},
    });
  },

  runTask(
    taskId: number,
    payload: {
      prompt: string;
      provider?: string;
      model?: string;
      system_prompt?: string;
      session_id?: string;
      conversation_id?: number;
      idempotency_key?: string;
      max_turns?: number;
      timeout_seconds?: number;
      trace_id?: string;
      actor?: string;
    },
  ): Promise<BackendTaskRun> {
    return request<BackendTaskRun>(`/tasks/${taskId}/run`, {
      method: 'POST',
      body: payload,
    });
  },

  getTaskStats(projectId = DEFAULT_PROJECT_ID): Promise<BackendTaskStats> {
    return request<BackendTaskStats>(`/tasks/stats${buildQuery({ project_id: projectId })}`);
  },

  listUpdates(projectId = DEFAULT_PROJECT_ID, limit = 20): Promise<BackendProjectUpdate[]> {
    return request<BackendProjectUpdate[]>(
      `/updates${buildQuery({ project_id: projectId, limit })}`,
    );
  },

  listInbox(projectId = DEFAULT_PROJECT_ID): Promise<BackendInboxItem[]> {
    return request<BackendInboxItem[]>(`/inbox${buildQuery({ project_id: projectId })}`);
  },

  markInboxRead(itemId: number): Promise<BackendInboxItem> {
    return request<BackendInboxItem>(`/inbox/${itemId}/read`, {
      method: 'PATCH',
      body: {},
    });
  },

  closeInboxItem(itemId: number, userInput?: string): Promise<BackendInboxItem> {
    return request<BackendInboxItem>(`/inbox/${itemId}/close`, {
      method: 'POST',
      body: userInput ? { user_input: userInput } : {},
    });
  },

  listConversations(
    projectId = DEFAULT_PROJECT_ID,
    agentId?: number,
    taskId?: number,
  ): Promise<ConversationSummary[]> {
    return request<BackendConversationList>(
      `/conversations${buildQuery({
        project_id: projectId,
        page_size: 50,
        agent_id: agentId,
        task_id: taskId,
      })}`,
    ).then(payload =>
      payload.items.map(item => ({
        id: item.id,
        title: item.title,
        status: item.status,
        agentId: item.agent_id,
        taskId: item.task_id,
        updatedAt: item.updated_at,
      })),
    );
  },

  createConversation(payload: {
    project_id: number;
    agent_id: number;
    task_id?: number | null;
    title: string;
  }): Promise<ConversationSummary> {
    return request<BackendConversationItem>('/conversations', {
      method: 'POST',
      body: payload,
    }).then(item => ({
      id: item.id,
      title: item.title,
      status: item.status,
      agentId: item.agent_id,
      taskId: item.task_id,
      updatedAt: item.updated_at,
    }));
  },

  getUsageBudget(): Promise<UsageBudget> {
    return request<BackendUsageBudget>('/usage/budget').then(payload => ({
      month: payload.month,
      budgetUsd: Number(payload.budget_usd),
      usedUsd: Number(payload.used_usd),
      remainingUsd: Number(payload.remaining_usd),
      utilizationRatio: payload.utilization_ratio,
    }));
  },

  getUsageTimeline(days = 7): Promise<UsageTimelinePoint[]> {
    return request<BackendUsageTimelinePoint[]>(`/usage/timeline${buildQuery({ days })}`).then(
      rows =>
        rows.map(row => ({
          date: row.date,
          totalRequestCount: row.total_request_count,
          providers: Object.fromEntries(
            Object.entries(row.providers).map(([provider, item]) => [
              provider,
              { requestCount: item.request_count, costUsd: Number(item.cost_usd) },
            ]),
          ),
        })),
    );
  },

  getUsageErrors(projectId = DEFAULT_PROJECT_ID): Promise<UsageError[]> {
    return request<BackendUsageError[]>(`/usage/errors${buildQuery({ project_id: projectId })}`).then(
      rows =>
        rows.map(row => ({
          timestamp: row.timestamp,
          modelId: row.model_id,
          errorType: row.error_type,
          message: row.message,
        })),
    );
  },

  getFilesTree(projectId = DEFAULT_PROJECT_ID, path = '.', maxDepth = 3): Promise<FileNode> {
    return request<BackendFilesTree>(
      `/files${buildQuery({ project_id: projectId, path, max_depth: maxDepth })}`,
    ).then(payload => toFileNode(payload.root));
  },

  getFileContent(projectId: number, fileId: string): Promise<BackendFileContent> {
    return request<BackendFileContent>(
      `/files/${encodeURIComponent(fileId)}/content${buildQuery({ project_id: projectId })}`,
    );
  },

  updateFilePermission(
    projectId: number,
    fileId: string,
    permission: PermissionLevel | 'inherit',
  ): Promise<{ permission: PermissionLevel }> {
    return request<{ permission: PermissionLevel }>(
      `/files/${encodeURIComponent(fileId)}/permissions`,
      {
        method: 'PATCH',
        body: {
          project_id: projectId,
          permission,
        },
      },
    );
  },

  listRoles(projectId = DEFAULT_PROJECT_ID): Promise<RoleProfile[]> {
    return request<BackendRole[]>(`/roles${buildQuery({ project_id: projectId })}`).then(rows =>
      rows.map(row => ({
        id: row.id,
        name: row.name,
        description: row.description,
        checkpointPreference: row.checkpoint_preference,
        tags: row.tags,
      })),
    );
  },

  createRole(
    projectId: number,
    payload: Omit<RoleProfile, 'id'>,
  ): Promise<RoleProfile> {
    return request<BackendRole>('/roles', {
      method: 'POST',
      body: {
        project_id: projectId,
        name: payload.name,
        description: payload.description,
        checkpoint_preference: payload.checkpointPreference,
        tags: payload.tags,
      },
    }).then(row => ({
      id: row.id,
      name: row.name,
      description: row.description,
      checkpointPreference: row.checkpoint_preference,
      tags: row.tags,
    }));
  },

  updateRole(
    projectId: number,
    role: RoleProfile,
  ): Promise<RoleProfile> {
    return request<BackendRole>(`/roles/${role.id}`, {
      method: 'PUT',
      body: {
        project_id: projectId,
        name: role.name,
        description: role.description,
        checkpoint_preference: role.checkpointPreference,
        tags: role.tags,
      },
    }).then(row => ({
      id: row.id,
      name: row.name,
      description: row.description,
      checkpointPreference: row.checkpoint_preference,
      tags: row.tags,
    }));
  },

  deleteRole(projectId: number, roleId: string): Promise<void> {
    return request<void>(`/roles/${roleId}${buildQuery({ project_id: projectId })}`, {
      method: 'DELETE',
    });
  },
};
