<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useChatStore } from '@/stores/chat';
import MessageItem from '@/components/chat/MessageItem.vue';
import ChatInput from '@/components/chat/ChatInput.vue';
import ToolConfirmation from '@/components/chat/ToolConfirmation.vue';

const store = useChatStore();
const messagesEndRef = ref<HTMLElement | null>(null);

function scrollToBottom() {
  nextTick(() => {
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' });
  });
}

// Watch for new messages to scroll
watch(() => store.messages.length, () => {
  scrollToBottom();
});

// Watch for loading state changes (sometimes new content appears without new message count)
watch(() => store.isLoading, () => {
  scrollToBottom();
});

async function handleSubmit(content: string) {
  store.sendMessage(content);
  scrollToBottom();
}

onMounted(() => {
  // Connect to conversation 1 by default for this view
  // In a full app, this would come from route params
  store.connect('1');
  scrollToBottom();
});

onUnmounted(() => {
  // Optional: close connection or handled by store/new connect
});
</script>

<template>
  <div class="flex flex-col h-full bg-bg-secondary text-text-primary font-sans">
    <!-- Header -->
    <header class="flex-none px-6 py-4 border-b border-border bg-bg-primary/50 backdrop-blur">
      <div class="flex items-center gap-3">
        <div class="w-3 h-3 rounded-full bg-red-500"></div>
        <div class="w-3 h-3 rounded-full bg-yellow-500"></div>
        <div class="w-3 h-3 rounded-full bg-green-500"></div>
        <span class="ml-4 font-mono text-sm font-bold text-text-secondary">Claude Code Clone</span>
      </div>
    </header>

    <!-- Messages Area -->
    <main class="flex-1 overflow-y-auto p-4 md:p-8 scrollbar-thin scrollbar-thumb-border">
      <div class="max-w-4xl mx-auto pb-4">
        <div v-if="store.messages.length === 0" class="text-center py-20 text-text-tertiary">
          <p class="text-2xl font-bold mb-2 text-text-primary">Welcome to Claude Code UI</p>
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
    <footer class="flex-none p-4 md:p-6 bg-bg-secondary border-t border-border/50">
      <ChatInput :is-loading="store.isLoading" @submit="handleSubmit" />
    </footer>

    <!-- Overlays -->
    <ToolConfirmation />
  </div>
</template>
