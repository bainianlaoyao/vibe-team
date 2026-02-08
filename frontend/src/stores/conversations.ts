import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { ApiRequestError, api } from '../services/api';
import { ConversationWebSocketClient } from '../services/websocket';
import type { ConversationMessage, ConversationSummary } from '../types';

function nowIso(): string {
  return new Date().toISOString();
}

function mapRole(role: string): 'user' | 'assistant' | 'system' {
  if (role === 'assistant') return 'assistant';
  if (role === 'system') return 'system';
  return 'user';
}

export const useConversationsStore = defineStore('conversations', () => {
  const projectId = ref<number>(api.getProjectId());
  const conversations = ref<ConversationSummary[]>([]);
  const activeConversationId = ref<number | null>(null);
  const messagesByConversation = ref<Record<number, ConversationMessage[]>>({});
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);
  const socketState = ref<'idle' | 'connecting' | 'connected' | 'reconnecting' | 'closed'>(
    'idle',
  );
  const streaming = ref<boolean>(false);
  const draft = ref<string>('');
  let tempMessageId = -1;
  let socketClient: ConversationWebSocketClient | null = null;

  const activeConversation = computed(
    () => conversations.value.find(item => item.id === activeConversationId.value) || null,
  );
  const activeMessages = computed(() =>
    activeConversationId.value ? messagesByConversation.value[activeConversationId.value] || [] : [],
  );

  async function ensureConversation(agentId: number): Promise<number> {
    if (activeConversationId.value) return activeConversationId.value;
    const created = await api.createConversation({
      project_id: projectId.value,
      agent_id: agentId,
      title: `Chat ${new Date().toLocaleTimeString()}`,
    });
    conversations.value = [created, ...conversations.value];
    activeConversationId.value = created.id;
    messagesByConversation.value[created.id] = [];
    return created.id;
  }

  function resetSocket(): void {
    if (socketClient) {
      socketClient.close();
      socketClient = null;
    }
    socketState.value = 'closed';
    streaming.value = false;
  }

  function connectSocket(conversationId: number): void {
    resetSocket();
    socketClient = new ConversationWebSocketClient(
      message => {
        if (!activeConversationId.value) return;
        const payload = message.payload || {};
        const targetId = activeConversationId.value;
        if (!messagesByConversation.value[targetId]) {
          messagesByConversation.value[targetId] = [];
        }
        if (message.type === 'assistant.chunk') {
          const content = String(payload.content || '');
          const items = messagesByConversation.value[targetId] || [];
          const last = items[items.length - 1];
          if (last && last.role === 'assistant' && last.messageType === 'stream_chunk') {
            last.content += content;
          } else {
            items.push({
              id: tempMessageId--,
              role: 'assistant',
              messageType: 'stream_chunk',
              content,
              createdAt: nowIso(),
            });
          }
          messagesByConversation.value[targetId] = [...items];
          streaming.value = true;
        } else if (message.type === 'assistant.complete') {
          streaming.value = false;
        } else if (message.type === 'session.error') {
          const info = String(payload.message || 'WebSocket error');
          error.value = info;
          streaming.value = false;
        }
      },
      state => {
        socketState.value = state;
      },
    );
    socketClient.connect(conversationId);
  }

  async function fetchConversations(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      conversations.value = await api.listConversations(projectId.value);
      if (conversations.value.length > 0 && !activeConversationId.value) {
        activeConversationId.value = conversations.value[0]?.id || null;
      }
      if (activeConversationId.value) {
        await fetchMessages(activeConversationId.value);
        connectSocket(activeConversationId.value);
      }
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to load conversations.';
    } finally {
      loading.value = false;
    }
  }

  async function fetchMessages(conversationId: number): Promise<void> {
    try {
      const rows = await api.listMessages(conversationId);
      messagesByConversation.value[conversationId] = rows.map(row => ({
        id: row.id,
        role: mapRole(row.role),
        messageType: row.messageType,
        content: row.content,
        createdAt: row.createdAt,
      }));
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to load messages.';
    }
  }

  async function setActiveConversation(conversationId: number): Promise<void> {
    activeConversationId.value = conversationId;
    await fetchMessages(conversationId);
    connectSocket(conversationId);
  }

  async function sendMessage(agentId: number): Promise<void> {
    const content = draft.value.trim();
    if (!content) return;
    draft.value = '';
    error.value = null;
    try {
      const conversationId = await ensureConversation(agentId);
      const optimistic: ConversationMessage = {
        id: tempMessageId--,
        role: 'user',
        messageType: 'text',
        content,
        createdAt: nowIso(),
      };
      messagesByConversation.value[conversationId] = [
        ...(messagesByConversation.value[conversationId] || []),
        optimistic,
      ];

      if (!socketClient || socketState.value === 'closed') {
        connectSocket(conversationId);
      }
      if (socketClient && socketState.value !== 'closed') {
        socketClient.send({ type: 'user.message', payload: { content } });
      } else {
        const persisted = await api.createMessage(conversationId, { role: 'user', content });
        messagesByConversation.value[conversationId] = [
          ...(messagesByConversation.value[conversationId] || []),
          persisted,
        ];
      }
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to send message.';
    }
  }

  function interrupt(): void {
    if (socketClient) {
      socketClient.send({ type: 'user.interrupt', payload: {} });
    }
  }

  return {
    projectId,
    conversations,
    activeConversationId,
    activeConversation,
    activeMessages,
    loading,
    error,
    socketState,
    streaming,
    draft,
    fetchConversations,
    fetchMessages,
    setActiveConversation,
    ensureConversation,
    sendMessage,
    interrupt,
    resetSocket,
  };
});
