export type Role = 'user' | 'assistant' | 'system';

export type ToolState = 'running' | 'requires_action' | 'completed' | 'failed';

export type InputRequestStatus = 'awaiting' | 'pending' | 'acknowledged' | 'error';

export type ConversationRuntimeState =
  | 'active'
  | 'streaming'
  | 'waiting_input'
  | 'interrupted'
  | 'error';

export type ChatSocketState = 'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed';

export interface ToolInvocation {
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  state: ToolState;
  result?: string;
  isError?: boolean;
}

export interface InputRequestCard {
  questionId: string;
  question: string;
  options: string[];
  required: boolean;
  metadata: Record<string, unknown>;
  inboxItemId: number | null;
  deadlineAt: string | null;
  answer: string;
  status: InputRequestStatus;
  errorMessage: string | null;
}

export type MessagePart =
  | { type: 'text'; content: string }
  | { type: 'thinking'; content: string; signature?: string }
  | { type: 'tool-invocation'; toolInvocation: ToolInvocation }
  | { type: 'request-input'; inputRequest: InputRequestCard }
  | { type: 'system-event'; subtype: string; data: Record<string, unknown> };

export interface ChatMessage {
  id: string;
  role: Role;
  parts: MessagePart[];
  timestamp: number;
  turnId: number | null;
}
