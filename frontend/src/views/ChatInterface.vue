<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { useChatStore } from '@/stores/chat';
import MessageItem from '@/components/chat/MessageItem.vue';
import ChatInput from '@/components/chat/ChatInput.vue';
import ToolConfirmation from '@/components/chat/ToolConfirmation.vue';

const store = useChatStore();
const messagesEndRef = ref<HTMLElement | null>(null);

function scrollToBottom() {
  messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' });
}

async function handleSubmit(content: string) {
  // Add user message
  store.addMessage({
    id: Date.now().toString(),
    role: 'user',
    parts: [{ type: 'text', content }],
    timestamp: Date.now()
  });

  // Mock assistant response for demo purposes
  setTimeout(() => {
    store.addMessage({
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      parts: [
        { type: 'thinking', content: 'Analyzing the user request...' },
        { type: 'text', content: 'Sure, I can help with that. Let me run a command.' },
        {
          type: 'tool-invocation',
          toolInvocation: {
            toolCallId: 'call_123',
            toolName: 'bash',
            args: { command: 'ls -la' },
            state: 'requires_action'
          }
        }
      ],
      timestamp: Date.now()
    });

    // Trigger approval flow
    store.requestToolApproval('call_123');
    scrollToBottom();
  }, 1000);

  scrollToBottom();
}

onMounted(() => {
  scrollToBottom();
});
</script>

<template>
  <div class="flex flex-col h-full bg-zinc-950 text-gray-100 font-sans">
    <!-- Header -->
    <header class="flex-none px-6 py-4 border-b border-zinc-800 bg-zinc-900/50 backdrop-blur">
      <div class="flex items-center gap-3">
        <div class="w-3 h-3 rounded-full bg-red-500"></div>
        <div class="w-3 h-3 rounded-full bg-yellow-500"></div>
        <div class="w-3 h-3 rounded-full bg-green-500"></div>
        <span class="ml-4 font-mono text-sm font-bold text-gray-400">Claude Code Clone</span>
      </div>
    </header>

    <!-- Messages Area -->
    <main class="flex-1 overflow-y-auto p-4 md:p-8 scrollbar-thin scrollbar-thumb-zinc-700">
      <div class="max-w-4xl mx-auto pb-4">
        <div v-if="store.messages.length === 0" class="text-center py-20 text-zinc-600">
          <p class="text-2xl font-bold mb-2">Welcome to Claude Code UI</p>
          <p>Start a conversation to see the tool integration in action.</p>
        </div>

        <MessageItem
          v-for="msg in store.messages"
          :key="msg.id"
          :message="msg"
        />

        <div ref="messagesEndRef" class="h-1"></div>
      </div>
    </main>

    <!-- Input Area -->
    <footer class="flex-none p-4 md:p-6 bg-zinc-950 border-t border-zinc-800/50">
      <ChatInput :is-loading="store.isLoading" @submit="handleSubmit" />
    </footer>

    <!-- Overlays -->
    <ToolConfirmation />
  </div>
</template>
