export type AgentType = 'claude' | 'gemini' | 'codex' | 'cursor' | 'custom';
export type AgentStatus = 'active' | 'busy' | 'blocked' | 'idle' | 'inactive';
export type TaskStatus =
  | 'todo'
  | 'in_progress'
  | 'review'
  | 'done'
  | 'blocked'
  | 'failed'
  | 'canceled';
export type TaskPriority = 'low' | 'medium' | 'high';
export type RiskFlag = 'stuck' | 'failing' | 'needs_review';
export type PermissionLevel = 'read' | 'write' | 'none';
export type ProjectStatus = 'active' | 'paused' | 'completed';

export interface Agent {
  id: string;
  apiId?: number;
  name: string;
  type: AgentType;
  avatar: string;
  status: AgentStatus;
  health: number;
  capabilities: string[];
  currentTasks: string[];
}

export interface Task {
  id: string;
  apiId?: number;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  assignedTo: string | null;
  dependencies: string[];
  blocks: string[];
  progress: number;
  riskFlags: RiskFlag[];
  changedFiles: string[];
  diffAdd: number;
  diffDel: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface DashboardStats {
  total: number;
  todo: number;
  running: number;
  review: number;
  done: number;
  blocked: number;
  failed: number;
  cancelled: number;
}

export interface ProjectUpdate {
  id: string;
  summary: string;
  agentId: string | null;
  time: string;
  filesChanged: string[];
}

export interface InboxItem {
  id: string;
  apiId: number;
  subject: string;
  preview: string;
  from: string;
  time: string;
  read: boolean;
  status: 'open' | 'closed';
}

export interface ConversationSummary {
  id: number;
  title: string;
  status: string;
  agentId: number;
  taskId: number | null;
  updatedAt: string;
}

export interface UsageBudget {
  month: string;
  budgetUsd: number;
  usedUsd: number;
  remainingUsd: number;
  utilizationRatio: number;
}

export interface UsageTimelinePoint {
  date: string;
  totalRequestCount: number;
  providers: Record<string, { requestCount: number; costUsd: number }>;
}

export interface UsageError {
  timestamp: string;
  modelId: string | null;
  errorType: string;
  message: string;
}

export interface FileNode {
  id: string;
  name: string;
  path: string;
  type: 'file' | 'folder';
  kind: string;
  sizeBytes: number | null;
  modifiedAt: string | null;
  owner: string;
  permission: PermissionLevel;
  children: FileNode[];
}

export interface RoleProfile {
  id: string;
  name: string;
  description: string;
  checkpointPreference: string;
  tags: string[];
}

export interface Project {
  id: string;
  name: string;
  description: string;
  status: ProjectStatus;
  tasks: Task[];
  agents: Agent[];
}

export interface ApiError {
  timestamp: Date;
  modelId: string;
  errorType: string;
  message: string;
}

export interface ApiUsage {
  modelId: string;
  modelName: string;
  requests: number;
  inputTokens: number;
  outputTokens: number;
  totalTokens: number;
  cost: number;
  avgLatency: number;
  successRate: number;
  errors: ApiError[];
}

export interface UsageDataPoint {
  date: string;
  claude: number;
  gemini: number;
  codex: number;
}

export interface ProjectDoc {
  id: string;
  name: string;
  updatedAtLabel: string;
}
