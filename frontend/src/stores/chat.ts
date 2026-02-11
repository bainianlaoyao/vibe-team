import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ChatMessage, ToolInvocation, MessagePart, Role } from '@/types/chat';

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([]);
  const isLoading = ref(false);
  const pendingToolCallId = ref<string | null>(null);
  const socket = ref<WebSocket | null>(null);
  const isConnected = ref(false);
  const currentConversationId = ref<string | null>(null);

  // Getters
  const pendingTool = computed(() => {
    if (!pendingToolCallId.value) return null;
    for (const msg of messages.value) {
      for (const part of msg.parts) {
        if (part.type === 'tool-invocation' &&
            part.toolInvocation?.toolCallId === pendingToolCallId.value) {
          return part.toolInvocation;
        }
      }
    }
    return null;
  });

  // Helper to find or create a message by turn_id (which we use as message ID)
  function getOrCreateMessage(turnId: string, role: Role, timestamp?: number): ChatMessage {
    let msg = messages.value.find(m => m.id === turnId);
    if (!msg) {
      msg = {
        id: turnId,
        role,
        parts: [],
        timestamp: timestamp || Date.now()
      };
      messages.value.push(msg);
    }
    return msg;
  }

  // Actions
  function addMessage(message: ChatMessage) {
    messages.value.push(message);
  }

  function updateToolState(toolCallId: string, updates: Partial<ToolInvocation>) {
    for (const msg of messages.value) {
      for (const part of msg.parts) {
        if (part.type === 'tool-invocation' && part.toolInvocation?.toolCallId === toolCallId) {
          Object.assign(part.toolInvocation, updates);
          return;
        }
      }
    }
  }

  function requestToolApproval(toolCallId: string) {
    pendingToolCallId.value = toolCallId;
    updateToolState(toolCallId, { state: 'requires_action' });
  }

  function approveTool(toolCallId: string) {
    if (!socket.value || !isConnected.value) return;

    pendingToolCallId.value = null;
    updateToolState(toolCallId, { state: 'running' });

    // For 'request_input' tools, we send the response back
    const msg = {
      type: 'user.input_response',
      payload: {
        question_id: toolCallId,
        answer: 'approved', // Or the actual input if this was a form
        resume_task: true
      }
    };
    socket.value.send(JSON.stringify(msg));
  }

  function denyTool(toolCallId: string) {
    if (!socket.value || !isConnected.value) return;

    pendingToolCallId.value = null;
    updateToolState(toolCallId, { state: 'failed', isError: true, result: 'User denied execution' });

    // Send cancel/deny response
    // If it was a request_input, we might want to send a specific denial or just interrupt
    // For this MVP, let's treat it as an interrupt or a specific denial response
    const msg = {
      type: 'user.interrupt',
      payload: {}
    };
    socket.value.send(JSON.stringify(msg));
  }

  function connect(conversationId: string) {
    if (socket.value) {
      socket.value.close();
    }

    currentConversationId.value = conversationId;
    messages.value = [];

    // Use relative path for WS to work with proxy or same origin
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // Assuming backend is proxy pass or same host in dev
    // If separate, might need env var. For now assuming proxy/same origin setup from prompt context implies standard web app structure
    const wsUrl = `${protocol}//${host}/api/ws/conversations/${conversationId}?protocol=v2`;

    console.log(`Connecting to ${wsUrl}`);
    socket.value = new WebSocket(wsUrl);

    socket.value.onopen = () => {
      isConnected.value = true;
      console.log('WS Connected');
    };

    socket.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleIncomingMessage(data);
      } catch (e) {
        console.error('Failed to parse WS message', e);
      }
    };

    socket.value.onclose = () => {
      isConnected.value = false;
      console.log('WS Disconnected');
    };

    socket.value.onerror = (err) => {
      console.error('WS Error', err);
    };
  }

  function sendMessage(content: string) {
    if (!socket.value || !isConnected.value) return;

    // Optimistically add message
    const tempId = 'temp-' + Date.now();
    addMessage({
      id: tempId,
      role: 'user',
      parts: [{ type: 'text', content }],
      timestamp: Date.now()
    });

    const msg = {
      type: 'user.message',
      payload: {
        content,
        metadata: {}
      }
    };
    socket.value.send(JSON.stringify(msg));
    isLoading.value = true;
  }

  function handleIncomingMessage(msg: any) {
    const { type, payload, turn_id } = msg;
    const turnIdStr = turn_id?.toString();

    switch (type) {
      case 'session.connected':
      case 'session.resumed':
        isLoading.value = false;
        break;

      case 'message.replay':
        // Reconstruct history
        // Payload: { message_id, role, message_type, content, metadata_json, created_at }
        handleReplayMessage(payload, turnIdStr);
        break;

      case 'assistant.chunk':
        if (turnIdStr) {
          const message = getOrCreateMessage(turnIdStr, 'assistant');
          // Append to last text part or create new
          const lastPart = message.parts[message.parts.length - 1];
          if (lastPart && lastPart.type === 'text') {
            lastPart.content += payload.content;
          } else {
            message.parts.push({ type: 'text', content: payload.content });
          }
          isLoading.value = true;
        }
        break;

      case 'assistant.thinking':
        if (turnIdStr) {
          const message = getOrCreateMessage(turnIdStr, 'assistant');
          const lastPart = message.parts[message.parts.length - 1];
          if (lastPart && lastPart.type === 'thinking') {
            lastPart.content += payload.content;
          } else {
            message.parts.push({ type: 'thinking', content: payload.content });
          }
          isLoading.value = true;
        }
        break;

      case 'assistant.tool_call':
        if (turnIdStr) {
          const message = getOrCreateMessage(turnIdStr, 'assistant');
          const toolInvocation: ToolInvocation = {
            toolCallId: payload.id,
            toolName: payload.name,
            args: payload.arguments,
            state: 'running'
          };
          message.parts.push({ type: 'tool-invocation', toolInvocation });
          isLoading.value = true;
        }
        break;

      case 'assistant.request_input':
        // This usually comes with a tool call block, or standalone
        // In the protocol, it's a specific message type.
        // We handle it by finding the tool call or creating a placeholder
        // For simplicity, we assume the tool_call event happened or we treat this as the trigger
        // The protocol sends 'assistant.tool_call' first with name='request_input' usually.
        // Then 'assistant.request_input' provides details.
        if (payload.question_id) {
           requestToolApproval(payload.question_id);
           isLoading.value = false;
        }
        break;

      case 'assistant.tool_result':
        updateToolState(payload.tool_id, {
          state: payload.is_error ? 'failed' : 'completed',
          result: payload.result,
          isError: payload.is_error
        });
        break;

      case 'assistant.complete':
        isLoading.value = false;
        break;

      case 'session.error':
        console.error('Session error:', payload);
        isLoading.value = false;
        break;
    }
  }

  function handleReplayMessage(payload: any, turnId: string) {
    if (!turnId) return;
    const timestamp = new Date(payload.created_at).getTime();
    const message = getOrCreateMessage(turnId, payload.role, timestamp);

    if (payload.message_type === 'text') {
      if (payload.metadata_json?.thinking) {
        message.parts.push({ type: 'thinking', content: payload.content });
      } else {
        message.parts.push({ type: 'text', content: payload.content });
      }
    } else if (payload.message_type === 'tool_call') {
      const toolInvocation: ToolInvocation = {
        toolCallId: payload.metadata_json?.tool_id || 'unknown',
        toolName: payload.content,
        args: payload.metadata_json?.arguments || {},
        state: 'completed' // Default to completed for history, unless we have state tracking
      };
      message.parts.push({ type: 'tool-invocation', toolInvocation });
    } else if (payload.message_type === 'tool_result') {
      // Update existing tool call in this message/turn if possible
      // Or just ignore if we assume tool_call was added and we just need state
      const toolId = payload.metadata_json?.tool_id;
      if (toolId) {
        updateToolState(toolId, {
          state: payload.metadata_json?.is_error ? 'failed' : 'completed',
          result: payload.content,
          isError: payload.metadata_json?.is_error
        });
      }
    }
  }

  return {
    messages,
    isLoading,
    pendingToolCallId,
    pendingTool,
    addMessage,
    updateToolState,
    requestToolApproval,
    approveTool,
    denyTool,
    connect,
    sendMessage
  };
});
