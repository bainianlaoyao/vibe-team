// Demo Event System Types
export type AgentStatus = 'idle' | 'thinking' | 'coding' | 'blocked' | 'done' | 'error'
export type AgentRole = 'backend' | 'frontend' | 'design' | 'architect'

export interface Agent {
  id: string
  name: string
  role: AgentRole
  status: AgentStatus
  currentAction: string
  artifacts: Artifact[]
  avatar: string
}

export interface Artifact {
  name: string
  path: string
  type: 'component' | 'page' | 'schema' | 'config' | 'style'
  timestamp: number
}

export interface DemoEvent {
  time_ms: number
  event: string
  [key: string]: any
}

export interface ProjectManifesto {
  name: string
  stack: string[]
  entities: string[]
  pages: string[]
  description: string
}

export interface PreviewState {
  type: 'loading' | 'skeleton' | 'partial' | 'full'
  elements: string[]
  currentView?: string
}

export interface Conflict {
  id: string
  type: 'schema' | 'dependency' | 'merge'
  agents: string[]
  description: string
  suggestion: string
  resolved: boolean
}

export type Tab = 'preview' | 'terminal' | 'diff'
