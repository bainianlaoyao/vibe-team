export type Role = 'user' | 'assistant' | 'system';

export type ToolState = 'running' | 'requires_action' | 'completed' | 'failed';

export interface ToolInvocation {
  toolCallId: string;
  toolName: string;
  args: Record<string, any>;
  state: ToolState;
  result?: any;
  isError?: boolean;
}

export interface MessagePart {
  type: 'text' | 'tool-invocation' | 'thinking';
  content?: string; // For text or thinking
  toolInvocation?: ToolInvocation;
}

export interface ChatMessage {
  id: string;
  role: Role;
  parts: MessagePart[];
  timestamp: number;
}

export interface ChatState {
  messages: ChatMessage[];
  isLoading: boolean;
  input: string;
  pendingToolCallId: string | null; // For permission interception
}
