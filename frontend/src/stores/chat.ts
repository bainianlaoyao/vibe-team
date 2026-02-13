import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { ApiRequestError, api } from '@/services/api';
import type { ConversationSummary } from '@/types';
import type {
  ChatMessage,
  ChatSocketState,
  ConversationRuntimeState,
  InputRequestCard,
  MessagePart,
  Role,
  ToolInvocation,
  ToolState,
} from '@/types/chat';

interface SocketEnvelope {
  type: string;
  conversation_id: number;
  turn_id: number | null;
  sequence: number;
  timestamp: string;
  trace_id: string;
  payload: Record<string, unknown>;
}

type OutboundMessage =
  | { type: 'user.message'; payload: { content: string; metadata: Record<string, unknown> } }
  | { type: 'user.input_response'; payload: { question_id: string; answer: string; resume_task: boolean } }
  | { type: 'user.interrupt'; payload: Record<string, never> }
  | { type: 'session.heartbeat'; payload: Record<string, never> };

const HEARTBEAT_MS = 30_000;
const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 12_000;

interface ChatAgentOption {
  id: number;
  name: string;
  status: string;
}

function parseRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function parseString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function parseStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === 'string');
}

function parseNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function normalizeRole(value: unknown): Role {
  if (value === 'assistant' || value === 'system' || value === 'user') return value;
  return 'assistant';
}

function normalizeRuntimeState(value: unknown): ConversationRuntimeState {
  if (
    value === 'active' ||
    value === 'streaming' ||
    value === 'waiting_input' ||
    value === 'interrupted' ||
    value === 'error'
  ) {
    return value;
  }
  return 'active';
}

function parseTimestampMs(iso: string): number {
  const parsed = Date.parse(iso);
  return Number.isNaN(parsed) ? Date.now() : parsed;
}

function buildWsBaseUrl(): string {
  const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api/v1';
  const url = new URL(apiBase);
  const scheme = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${scheme}//${url.host}`;
}

export const useChatStore = defineStore('chat', () => {
  const agents = ref<ChatAgentOption[]>([]);
  const selectedAgentId = ref<number | null>(null);
  const conversations = ref<ConversationSummary[]>([]);
  const messages = ref<ChatMessage[]>([]);
  const isLoading = ref(false);
  const error = ref<string | null>(null);
  const socketState = ref<ChatSocketState>('idle');
  const runtimeState = ref<ConversationRuntimeState>('active');
  const currentConversationId = ref<number | null>(null);
  const lastMessageSequence = ref(0);

  const canInterrupt = computed(() => runtimeState.value === 'streaming');
  const selectedAgent = computed(() =>
    agents.value.find(agent => agent.id === selectedAgentId.value) ?? null,
  );
  const currentConversation = computed(() =>
    conversations.value.find(item => item.id === currentConversationId.value) ?? null,
  );

  const pendingInputRequests = computed(() =>
    messages.value
      .flatMap(message => message.parts)
      .filter((part): part is Extract<MessagePart, { type: 'request-input' }> => part.type === 'request-input')
      .map(part => part.inputRequest)
      .filter(card => card.status === 'awaiting' || card.status === 'pending'),
  );

  let socket: WebSocket | null = null;
  let reconnectTimer: number | null = null;
  let heartbeatTimer: number | null = null;
  let reconnectAttempt = 0;
  let clientId = '';
  let manualClose = false;
  const outboundQueue: OutboundMessage[] = [];
  const seenMessageSequences = new Set<number>();
  const pendingUserOptimisticQueue: string[] = [];
  const pendingInputOptimisticByQuestion = new Map<string, string>();

  function sortMessagesByTime(): void {
    messages.value.sort((a, b) => a.timestamp - b.timestamp);
  }

  function sortConversationsByUpdatedAt(): void {
    conversations.value.sort((a, b) => parseTimestampMs(b.updatedAt) - parseTimestampMs(a.updatedAt));
  }

  function newTempId(prefix: string): string {
    return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  }

  function resetConversationState(): void {
    messages.value = [];
    seenMessageSequences.clear();
    outboundQueue.length = 0;
    pendingUserOptimisticQueue.length = 0;
    pendingInputOptimisticByQuestion.clear();
    lastMessageSequence.value = 0;
    setRuntimeState('active');
  }

  function ensureMessageByTurn(role: Role, turnId: number, timestampMs: number): ChatMessage {
    const key = `${role}-turn-${turnId}`;
    let message = messages.value.find(item => item.id === key);
    if (!message) {
      message = {
        id: key,
        role,
        parts: [],
        timestamp: timestampMs,
        turnId,
      };
      messages.value.push(message);
      sortMessagesByTime();
    }
    return message;
  }

  function addStandaloneMessage(role: Role, content: string, timestampMs: number): ChatMessage {
    const message: ChatMessage = {
      id: newTempId(`${role}-msg`),
      role,
      parts: [{ type: 'text', content }],
      timestamp: timestampMs,
      turnId: null,
    };
    messages.value.push(message);
    sortMessagesByTime();
    return message;
  }

  function markSequenceSeen(sequence: number | null): boolean {
    if (sequence === null || sequence <= 0) return false;
    if (seenMessageSequences.has(sequence)) return true;
    seenMessageSequences.add(sequence);
    if (sequence > lastMessageSequence.value) {
      lastMessageSequence.value = sequence;
    }
    return false;
  }

  function parseMessageSequence(payload: Record<string, unknown>): number | null {
    return parseNumber(payload.message_sequence);
  }

  function findToolInvocation(toolCallId: string): ToolInvocation | null {
    for (const message of messages.value) {
      for (const part of message.parts) {
        if (part.type === 'tool-invocation' && part.toolInvocation.toolCallId === toolCallId) {
          return part.toolInvocation;
        }
      }
    }
    return null;
  }

  function updateToolInvocation(toolCallId: string, patch: Partial<ToolInvocation>): void {
    const target = findToolInvocation(toolCallId);
    if (!target) return;
    Object.assign(target, patch);
  }

  function findInputCard(questionId: string): InputRequestCard | null {
    for (const message of messages.value) {
      for (const part of message.parts) {
        if (part.type === 'request-input' && part.inputRequest.questionId === questionId) {
          return part.inputRequest;
        }
      }
    }
    return null;
  }

  function upsertInputCard(
    message: ChatMessage,
    payload: {
      questionId: string;
      question: string;
      options: string[];
      required: boolean;
      metadata: Record<string, unknown>;
      inboxItemId: number | null;
      deadlineAt: string | null;
    },
  ): void {
    const existing = findInputCard(payload.questionId);
    if (existing) {
      existing.question = payload.question;
      existing.options = payload.options;
      existing.required = payload.required;
      existing.metadata = payload.metadata;
      existing.inboxItemId = payload.inboxItemId;
      existing.deadlineAt = payload.deadlineAt;
      if (existing.status === 'error') {
        existing.status = 'awaiting';
        existing.errorMessage = null;
      }
      return;
    }

    message.parts.push({
      type: 'request-input',
      inputRequest: {
        questionId: payload.questionId,
        question: payload.question,
        options: payload.options,
        required: payload.required,
        metadata: payload.metadata,
        inboxItemId: payload.inboxItemId,
        deadlineAt: payload.deadlineAt,
        answer: '',
        status: 'awaiting',
        errorMessage: null,
      },
    });
  }

  function updateQuestionStatus(
    questionId: string,
    patch: Partial<InputRequestCard>,
  ): void {
    const card = findInputCard(questionId);
    if (!card) return;
    Object.assign(card, patch);
  }

  function markLatestPendingQuestionAsError(message: string): void {
    const pendingCards = pendingInputRequests.value;
    const latest = pendingCards[pendingCards.length - 1];
    if (!latest) return;
    latest.status = 'error';
    latest.errorMessage = message;
  }

  function setRuntimeState(next: ConversationRuntimeState): void {
    runtimeState.value = next;
    isLoading.value = next === 'streaming';
  }

  function clearSocketTimers(): void {
    if (heartbeatTimer !== null) {
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = null;
    }
    if (reconnectTimer !== null) {
      window.clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  function closeSocket(): void {
    clearSocketTimers();
    if (socket) {
      socket.close(1000, 'client close');
      socket = null;
    }
  }

  function closeSocketSilently(): void {
    clearSocketTimers();
    if (!socket) return;
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    socket.close(1000, 'replace socket');
    socket = null;
  }

  function disconnectActiveConversation(): void {
    clearSocketTimers();
    closeSocketSilently();
    currentConversationId.value = null;
    socketState.value = 'idle';
    resetConversationState();
  }

  function buildSocketUrl(conversationId: number): string {
    const params = new URLSearchParams();
    params.set('protocol', 'v2');
    params.set('client_id', clientId);
    params.set('last_sequence', String(lastMessageSequence.value));
    return `${buildWsBaseUrl()}/ws/conversations/${conversationId}?${params.toString()}`;
  }

  function enqueueOrSend(message: OutboundMessage): void {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message));
      return;
    }
    outboundQueue.push(message);
  }

  function flushOutboundQueue(): void {
    while (outboundQueue.length > 0 && socket && socket.readyState === WebSocket.OPEN) {
      const next = outboundQueue.shift();
      if (!next) break;
      socket.send(JSON.stringify(next));
    }
  }

  function startHeartbeat(): void {
    heartbeatTimer = window.setInterval(() => {
      enqueueOrSend({ type: 'session.heartbeat', payload: {} });
    }, HEARTBEAT_MS);
  }

  function scheduleReconnect(): void {
    if (manualClose || currentConversationId.value === null) return;
    socketState.value = 'reconnecting';
    const delay = Math.min(RECONNECT_BASE_MS * 2 ** reconnectAttempt, RECONNECT_MAX_MS);
    reconnectAttempt += 1;
    reconnectTimer = window.setTimeout(() => {
      connect(currentConversationId.value as number, false);
    }, delay);
  }

  function bindSocket(socketInstance: WebSocket): void {
    socketInstance.onopen = () => {
      socketState.value = 'connected';
      reconnectAttempt = 0;
      flushOutboundQueue();
      startHeartbeat();
    };

    socketInstance.onmessage = event => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(String(event.data));
      } catch {
        error.value = 'Invalid websocket payload.';
        return;
      }
      handleIncomingEnvelope(parsed);
    };

    socketInstance.onerror = () => {
      socketState.value = 'reconnecting';
    };

    socketInstance.onclose = () => {
      clearSocketTimers();
      socket = null;
      if (manualClose) {
        socketState.value = 'closed';
        return;
      }
      scheduleReconnect();
    };
  }

  function connect(conversationId: number, resetHistory: boolean): void {
    manualClose = false;
    clearSocketTimers();
    closeSocketSilently();

    if (!clientId || currentConversationId.value !== conversationId) {
      clientId = `web-${conversationId}-${Date.now().toString(36)}`;
    }
    if (resetHistory) {
      resetConversationState();
    }

    currentConversationId.value = conversationId;
    socketState.value = 'connecting';
    const ws = new WebSocket(buildSocketUrl(conversationId));
    socket = ws;
    bindSocket(ws);
  }

  function parseEnvelope(raw: unknown): SocketEnvelope | null {
    const data = parseRecord(raw);
    const type = parseString(data.type);
    const conversationId = parseNumber(data.conversation_id);
    const sequence = parseNumber(data.sequence);
    const timestamp = parseString(data.timestamp);
    const traceId = parseString(data.trace_id);
    const payload = parseRecord(data.payload);

    if (!type || conversationId === null || sequence === null || !timestamp || !traceId) {
      return null;
    }

    return {
      type,
      conversation_id: conversationId,
      turn_id: parseNumber(data.turn_id),
      sequence,
      timestamp,
      trace_id: traceId,
      payload,
    };
  }

  function handleIncomingEnvelope(raw: unknown): void {
    const envelope = parseEnvelope(raw);
    if (!envelope) {
      error.value = 'Invalid websocket envelope.';
      return;
    }

    const messageSequence = parseMessageSequence(envelope.payload);
    if (markSequenceSeen(messageSequence)) {
      return;
    }

    switch (envelope.type) {
      case 'session.connected':
      case 'session.resumed': {
        setRuntimeState(normalizeRuntimeState(envelope.payload.state));
        error.value = null;
        return;
      }
      case 'session.state': {
        setRuntimeState(normalizeRuntimeState(envelope.payload.state));
        return;
      }
      case 'session.heartbeat_ack': {
        return;
      }
      case 'user.message.ack': {
        handleUserMessageAck(envelope);
        return;
      }
      case 'user.input_response.ack': {
        handleInputResponseAck(envelope);
        return;
      }
      case 'user.interrupt.ack': {
        isLoading.value = false;
        return;
      }
      case 'assistant.chunk': {
        handleAssistantChunk(envelope);
        return;
      }
      case 'assistant.thinking': {
        handleAssistantThinking(envelope);
        return;
      }
      case 'assistant.tool_call': {
        handleToolCall(envelope);
        return;
      }
      case 'assistant.tool_result': {
        handleToolResult(envelope);
        return;
      }
      case 'assistant.request_input': {
        handleRequestInput(envelope);
        return;
      }
      case 'assistant.complete': {
        isLoading.value = false;
        return;
      }
      case 'session.system_event': {
        handleSystemEvent(envelope);
        return;
      }
      case 'message.replay': {
        handleReplayMessage(envelope);
        return;
      }
      case 'session.error': {
        const code = parseString(envelope.payload.code);
        const message = parseString(envelope.payload.message) || 'Conversation error';
        error.value = code ? `${code}: ${message}` : message;
        isLoading.value = false;
        markLatestPendingQuestionAsError(message);
        return;
      }
      default:
        return;
    }
  }

  function handleUserMessageAck(envelope: SocketEnvelope): void {
    const turnId = envelope.turn_id;
    const optimisticId = pendingUserOptimisticQueue.shift();
    if (!optimisticId) return;
    const optimistic = messages.value.find(item => item.id === optimisticId);
    if (!optimistic) return;
    if (turnId !== null) {
      optimistic.id = `user-turn-${turnId}`;
      optimistic.turnId = turnId;
    }
  }

  function handleInputResponseAck(envelope: SocketEnvelope): void {
    const questionId = parseString(envelope.payload.question_id);
    if (questionId) {
      updateQuestionStatus(questionId, { status: 'acknowledged', errorMessage: null });
      updateToolInvocation(questionId, { state: 'completed' });
      const optimisticId = pendingInputOptimisticByQuestion.get(questionId);
      if (optimisticId) {
        const optimistic = messages.value.find(item => item.id === optimisticId);
        if (optimistic && envelope.turn_id !== null) {
          optimistic.id = `user-turn-${envelope.turn_id}`;
          optimistic.turnId = envelope.turn_id;
        }
        pendingInputOptimisticByQuestion.delete(questionId);
      }
    }
  }

  function handleAssistantChunk(envelope: SocketEnvelope): void {
    if (envelope.turn_id === null) return;
    const content = parseString(envelope.payload.content);
    if (!content) return;

    const message = ensureMessageByTurn('assistant', envelope.turn_id, parseTimestampMs(envelope.timestamp));
    const lastPart = message.parts[message.parts.length - 1];
    if (lastPart && lastPart.type === 'text') {
      lastPart.content += content;
    } else {
      message.parts.push({ type: 'text', content });
    }
    isLoading.value = true;
  }

  function handleAssistantThinking(envelope: SocketEnvelope): void {
    if (envelope.turn_id === null) return;
    const content = parseString(envelope.payload.content);
    if (!content) return;
    const signature = parseString(envelope.payload.signature);
    const message = ensureMessageByTurn('assistant', envelope.turn_id, parseTimestampMs(envelope.timestamp));
    const lastPart = message.parts[message.parts.length - 1];
    if (lastPart && lastPart.type === 'thinking') {
      lastPart.content += content;
    } else {
      message.parts.push({ type: 'thinking', content, signature: signature || undefined });
    }
    isLoading.value = true;
  }

  function resolveToolStateFromResult(isError: boolean): ToolState {
    return isError ? 'failed' : 'completed';
  }

  function handleToolCall(envelope: SocketEnvelope): void {
    if (envelope.turn_id === null) return;
    const toolCallId = parseString(envelope.payload.id);
    const name = parseString(envelope.payload.name);
    if (!toolCallId || !name) return;
    const args = parseRecord(envelope.payload.arguments);

    const message = ensureMessageByTurn('assistant', envelope.turn_id, parseTimestampMs(envelope.timestamp));
    if (findToolInvocation(toolCallId)) {
      updateToolInvocation(toolCallId, { toolName: name, args, state: 'running' });
      return;
    }

    message.parts.push({
      type: 'tool-invocation',
      toolInvocation: {
        toolCallId,
        toolName: name,
        args,
        state: 'running',
      },
    });
    isLoading.value = true;
  }

  function handleToolResult(envelope: SocketEnvelope): void {
    const toolId = parseString(envelope.payload.tool_id);
    if (!toolId) return;
    const isError = Boolean(envelope.payload.is_error);
    const result = parseString(envelope.payload.result);
    updateToolInvocation(toolId, {
      state: resolveToolStateFromResult(isError),
      result,
      isError,
    });
  }

  function handleRequestInput(envelope: SocketEnvelope): void {
    if (envelope.turn_id === null) return;
    const questionId = parseString(envelope.payload.question_id);
    if (!questionId) return;
    const question = parseString(envelope.payload.question);
    const options = parseStringArray(envelope.payload.options);
    const required = Boolean(envelope.payload.required);
    const metadata = parseRecord(envelope.payload.metadata);
    const inboxItemId = parseNumber(envelope.payload.inbox_item_id);
    const deadlineAtRaw = parseString(envelope.payload.deadline_at);
    const deadlineAt = deadlineAtRaw || null;

    const message = ensureMessageByTurn('assistant', envelope.turn_id, parseTimestampMs(envelope.timestamp));
    upsertInputCard(message, {
      questionId,
      question,
      options,
      required,
      metadata,
      inboxItemId,
      deadlineAt,
    });
    updateToolInvocation(questionId, { state: 'requires_action' });
    isLoading.value = false;
  }

  function handleSystemEvent(envelope: SocketEnvelope): void {
    const subtype = parseString(envelope.payload.subtype) || 'system_event';
    const data = parseRecord(envelope.payload.data);
    const turnId = envelope.turn_id ?? 0;
    const message = ensureMessageByTurn('system', turnId, parseTimestampMs(envelope.timestamp));
    message.parts.push({ type: 'system-event', subtype, data });
  }

  function handleReplayMessage(envelope: SocketEnvelope): void {
    const role = normalizeRole(envelope.payload.role);
    const messageType = parseString(envelope.payload.message_type);
    const content = parseString(envelope.payload.content);
    const metadata = parseRecord(envelope.payload.metadata_json);
    const createdAt = parseString(envelope.payload.created_at) || envelope.timestamp;
    const timestampMs = parseTimestampMs(createdAt);
    const turnId = parseNumber(metadata.turn_id);

    if (messageType === 'tool_result') {
      const toolId = parseString(metadata.tool_id);
      if (toolId) {
        const isError = Boolean(metadata.is_error);
        updateToolInvocation(toolId, {
          state: resolveToolStateFromResult(isError),
          result: content,
          isError,
        });
      }
      return;
    }

    if (messageType === 'tool_call') {
      if (turnId === null) return;
      const message = ensureMessageByTurn(role, turnId, timestampMs);
      const toolId = parseString(metadata.tool_id);
      if (!toolId) return;
      if (findToolInvocation(toolId)) return;
      message.parts.push({
        type: 'tool-invocation',
        toolInvocation: {
          toolCallId: toolId,
          toolName: content || parseString(metadata.name) || 'tool',
          args: parseRecord(metadata.arguments),
          state: 'completed',
        },
      });
      return;
    }

    if (messageType === 'input_request') {
      if (turnId === null) return;
      const message = ensureMessageByTurn(role, turnId, timestampMs);
      const questionId = parseString(metadata.question_id);
      if (!questionId) return;
      upsertInputCard(message, {
        questionId,
        question: content,
        options: parseStringArray(metadata.options),
        required: Boolean(metadata.required),
        metadata: parseRecord(metadata.metadata),
        inboxItemId: parseNumber(metadata.inbox_item_id),
        deadlineAt: parseString(metadata.deadline_at) || null,
      });
      updateToolInvocation(questionId, { state: 'requires_action' });
      return;
    }

    if (messageType === 'input_response') {
      const questionId = parseString(metadata.question_id);
      if (questionId) {
        updateQuestionStatus(questionId, {
          answer: content,
          status: 'acknowledged',
          errorMessage: null,
        });
      }
    }

    if (messageType === 'text' && metadata.thinking === true) {
      if (turnId === null) {
        addStandaloneMessage(role, content, timestampMs);
        return;
      }
      const message = ensureMessageByTurn(role, turnId, timestampMs);
      const lastPart = message.parts[message.parts.length - 1];
      if (lastPart && lastPart.type === 'thinking') {
        lastPart.content += content;
      } else {
        message.parts.push({
          type: 'thinking',
          content,
          signature: parseString(metadata.signature) || undefined,
        });
      }
      return;
    }

    if (messageType === 'text' && role === 'system' && metadata.system_data) {
      const message = ensureMessageByTurn('system', turnId ?? 0, timestampMs);
      message.parts.push({
        type: 'system-event',
        subtype: content || 'system_event',
        data: parseRecord(metadata.system_data),
      });
      return;
    }

    if (messageType === 'interrupt') {
      const message = ensureMessageByTurn('system', turnId ?? 0, timestampMs);
      message.parts.push({ type: 'system-event', subtype: 'interrupt', data: {} });
      return;
    }

    if (turnId === null) {
      addStandaloneMessage(role, content, timestampMs);
      return;
    }

    const message = ensureMessageByTurn(role, turnId, timestampMs);
    const lastPart = message.parts[message.parts.length - 1];
    if (lastPart && lastPart.type === 'text') {
      lastPart.content += content;
    } else {
      message.parts.push({ type: 'text', content });
    }
  }

  function newConversationTitle(): string {
    return `Chat ${new Date().toLocaleTimeString()}`;
  }

  async function refreshConversationsForAgent(agentId: number, projectId: number): Promise<void> {
    conversations.value = await api.listConversations(projectId, agentId);
    sortConversationsByUpdatedAt();
  }

  async function bootstrapConversation(): Promise<void> {
    error.value = null;
    try {
      const projectId = api.getProjectId();
      const agentRows = await api.listAgents(projectId);
      agents.value = agentRows.map(row => ({
        id: row.id,
        name: row.name,
        status: row.status,
      }));

      if (agents.value.length === 0) {
        throw new Error('No available agent to start conversation.');
      }

      if (
        selectedAgentId.value === null ||
        !agents.value.some(agent => agent.id === selectedAgentId.value)
      ) {
        selectedAgentId.value = agents.value[0]?.id ?? null;
      }

      const activeAgentId = selectedAgentId.value;
      if (activeAgentId === null) {
        throw new Error('No available agent to start conversation.');
      }

      await refreshConversationsForAgent(activeAgentId, projectId);

      let conversationId = currentConversationId.value;
      if (conversationId !== null && !conversations.value.some(item => item.id === conversationId)) {
        conversationId = null;
      }
      if (conversationId === null) {
        conversationId = conversations.value[0]?.id ?? null;
      }

      if (conversationId === null) {
        const created = await api.createConversation({
          project_id: projectId,
          agent_id: activeAgentId,
          title: newConversationTitle(),
        });
        conversations.value = [created];
        conversationId = created.id;
      }

      connect(conversationId, true);
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to bootstrap conversation.';
    }
  }

  async function selectAgent(agentId: number, forceReload = false): Promise<void> {
    if (!agents.value.some(agent => agent.id === agentId)) {
      error.value = 'Selected agent does not exist.';
      return;
    }
    if (
      !forceReload &&
      selectedAgentId.value === agentId &&
      conversations.value.length > 0 &&
      currentConversationId.value !== null
    ) {
      return;
    }

    error.value = null;
    selectedAgentId.value = agentId;
    disconnectActiveConversation();

    try {
      const projectId = api.getProjectId();
      await refreshConversationsForAgent(agentId, projectId);
      const nextConversationId = conversations.value[0]?.id ?? null;
      if (nextConversationId !== null) {
        connect(nextConversationId, true);
      }
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to switch agent conversations.';
    }
  }

  async function selectConversation(conversationId: number): Promise<void> {
    let target = conversations.value.find(item => item.id === conversationId) ?? null;
    if (!target) {
      const activeAgentId = selectedAgentId.value;
      if (activeAgentId !== null) {
        try {
          await refreshConversationsForAgent(activeAgentId, api.getProjectId());
        } catch (cause) {
          const apiError = cause instanceof ApiRequestError ? cause : null;
          error.value = apiError
            ? `${apiError.code}: ${apiError.message}`
            : 'Failed to refresh conversation list.';
          return;
        }
        target = conversations.value.find(item => item.id === conversationId) ?? null;
      }
    }
    if (!target) {
      error.value = 'Selected conversation does not exist in current agent list.';
      return;
    }
    if (currentConversationId.value === conversationId) {
      return;
    }

    error.value = null;
    selectedAgentId.value = target.agentId;
    connect(conversationId, true);
  }

  async function createConversationForSelectedAgent(): Promise<void> {
    if (selectedAgentId.value === null) {
      error.value = 'Select an agent before creating a conversation.';
      return;
    }

    error.value = null;
    try {
      const projectId = api.getProjectId();
      const created = await api.createConversation({
        project_id: projectId,
        agent_id: selectedAgentId.value,
        title: newConversationTitle(),
      });
      conversations.value = [created, ...conversations.value.filter(item => item.id !== created.id)];
      sortConversationsByUpdatedAt();
      connect(created.id, true);
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to create conversation.';
    }
  }

  function sendMessage(content: string): void {
    const trimmed = content.trim();
    if (!trimmed) return;
    if (currentConversationId.value === null) {
      error.value = 'Please select or create a conversation first.';
      return;
    }
    error.value = null;
    const optimistic = addStandaloneMessage('user', trimmed, Date.now());
    pendingUserOptimisticQueue.push(optimistic.id);
    enqueueOrSend({
      type: 'user.message',
      payload: {
        content: trimmed,
        metadata: {},
      },
    });
    isLoading.value = true;
  }

  function submitInputResponse(questionId: string, answer: string): void {
    const card = findInputCard(questionId);
    if (!card) return;
    const trimmedAnswer = answer.trim();
    if (card.required && !trimmedAnswer) {
      card.status = 'error';
      card.errorMessage = 'Answer is required.';
      return;
    }

    card.answer = trimmedAnswer;
    card.status = 'pending';
    card.errorMessage = null;

    const optimistic = addStandaloneMessage('user', trimmedAnswer, Date.now());
    pendingInputOptimisticByQuestion.set(questionId, optimistic.id);

    enqueueOrSend({
      type: 'user.input_response',
      payload: {
        question_id: questionId,
        answer: trimmedAnswer,
        resume_task: true,
      },
    });
  }

  function interrupt(): void {
    if (!canInterrupt.value) return;
    enqueueOrSend({ type: 'user.interrupt', payload: {} });
  }

  function connectByConversationId(conversationId: number): void {
    void selectConversation(conversationId);
  }

  function resetConnection(): void {
    manualClose = true;
    closeSocket();
    socketState.value = 'closed';
    isLoading.value = false;
  }

  return {
    agents,
    selectedAgentId,
    selectedAgent,
    conversations,
    currentConversation,
    messages,
    isLoading,
    error,
    socketState,
    runtimeState,
    currentConversationId,
    canInterrupt,
    pendingInputRequests,
    lastMessageSequence,
    bootstrapConversation,
    selectAgent,
    selectConversation,
    createConversationForSelectedAgent,
    connectByConversationId,
    sendMessage,
    submitInputResponse,
    interrupt,
    resetConnection,
  };
});
