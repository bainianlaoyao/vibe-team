import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ChatMessage, ToolInvocation, ToolState } from '@/types/chat';

export const useChatStore = defineStore('chat', () => {
  const messages = ref<ChatMessage[]>([]);
  const isLoading = ref(false);
  const pendingToolCallId = ref<string | null>(null);

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

  // Actions
  function addMessage(message: ChatMessage) {
    messages.value.push(message);
  }

  function appendToLastMessage(content: string) {
    const lastMsg = messages.value[messages.value.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
        // Try to append to the last text part
        const lastPart = lastMsg.parts[lastMsg.parts.length - 1];
        if (lastPart.type === 'text') {
            lastPart.content = (lastPart.content || '') + content;
            return;
        }
    }
    // Otherwise logic to add new part or new message would go here
    // For now, simple state updates
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
    pendingToolCallId.value = null;
    updateToolState(toolCallId, { state: 'running' });
    // TODO: Notify backend
  }

  function denyTool(toolCallId: string) {
    pendingToolCallId.value = null;
    updateToolState(toolCallId, { state: 'failed', isError: true, result: 'User denied execution' });
    // TODO: Notify backend
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
    denyTool
  };
});
