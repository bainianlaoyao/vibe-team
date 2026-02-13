<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, nextTick, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useChatStore } from '@/stores/chat';
import MessageItem from '@/components/chat/MessageItem.vue';
import ChatInput from '@/components/chat/ChatInput.vue';

const store = useChatStore();
const route = useRoute();
const messagesEndRef = ref<HTMLElement | null>(null);
const initialized = ref(false);
const connectionLabel = computed(() =>
  store.socketState === 'connected' ? 'Connected' : `WS ${store.socketState}`,
);
const statusLabel = computed(() => `Runtime: ${store.runtimeState}`);
const currentAgentLabel = computed(() =>
  store.selectedAgent === null ? 'No agent' : `${store.selectedAgent.name} (#${store.selectedAgent.id})`,
);
const currentConversationLabel = computed(() =>
  store.currentConversation === null
    ? 'No conversation'
    : `${store.currentConversation.title} (#${store.currentConversation.id})`,
);

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
watch(
  () => store.messages,
  () => {
    scrollToBottom();
  },
  { deep: true },
);

async function handleSubmit(content: string) {
  store.sendMessage(content);
  scrollToBottom();
}

function handleInputSubmit(payload: { questionId: string; answer: string }) {
  store.submitInputResponse(payload.questionId, payload.answer);
}

function handleAgentChange(event: Event) {
  const value = Number((event.target as HTMLSelectElement).value);
  if (!Number.isFinite(value) || value <= 0) return;
  void store.selectAgent(value);
}

function handleConversationChange(event: Event) {
  const value = Number((event.target as HTMLSelectElement).value);
  if (!Number.isFinite(value) || value <= 0) return;
  void store.selectConversation(value);
}

function handleCreateConversation() {
  void store.createConversationForSelectedAgent();
}

function parsePositiveIntQuery(raw: unknown): number | null {
  const value = Array.isArray(raw) ? raw[0] : raw;
  if (typeof value !== 'string') return null;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0) return null;
  return parsed;
}

async function syncConversationFromRoute(): Promise<void> {
  const agentId = parsePositiveIntQuery(route.query.agent);
  const conversationId = parsePositiveIntQuery(route.query.conversation);

  if (agentId !== null) {
    await store.selectAgent(agentId, conversationId !== null);
  }
  if (conversationId !== null) {
    await store.selectConversation(conversationId);
  }
}

onMounted(async () => {
  await store.bootstrapConversation();
  await syncConversationFromRoute();
  initialized.value = true;
  scrollToBottom();
});

watch(
  () => [route.query.agent, route.query.conversation],
  () => {
    if (!initialized.value) return;
    void syncConversationFromRoute();
  },
);

onUnmounted(() => {
  store.resetConnection();
});
</script>

<template>
  <div class="flex flex-col h-full bg-bg-secondary text-text-primary font-sans">
    <!-- Header -->
    <header class="flex-none px-6 py-4 border-b border-border bg-bg-primary/50 backdrop-blur">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div class="flex flex-col gap-2">
          <div class="flex items-center gap-3">
            <div class="h-2.5 w-2.5 rounded-full bg-emerald-500"></div>
            <span class="font-mono text-sm font-bold text-text-secondary">Conversation v2</span>
            <span class="text-xs text-text-tertiary">{{ currentAgentLabel }}</span>
            <span class="text-xs text-text-tertiary">{{ currentConversationLabel }}</span>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <select
              :value="store.selectedAgentId ?? ''"
              class="rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary"
              @change="handleAgentChange"
            >
              <option
                v-for="agent in store.agents"
                :key="agent.id"
                :value="agent.id"
              >
                {{ agent.name }}
              </option>
            </select>
            <select
              :value="store.currentConversationId ?? ''"
              class="min-w-52 rounded-md border border-border bg-bg-secondary px-2 py-1 text-xs text-text-primary disabled:cursor-not-allowed disabled:opacity-60"
              :disabled="store.conversations.length === 0"
              @change="handleConversationChange"
            >
              <option v-if="store.conversations.length === 0" value="" disabled>
                No conversations
              </option>
              <option
                v-for="conversation in store.conversations"
                :key="conversation.id"
                :value="conversation.id"
              >
                #{{ conversation.id }} {{ conversation.title }}
              </option>
            </select>
            <button
              type="button"
              class="rounded-md border border-border px-2 py-1 text-xs text-text-secondary disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="store.selectedAgentId === null"
              @click="handleCreateConversation"
            >
              New Conversation
            </button>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-text-tertiary">{{ connectionLabel }}</span>
          <span class="text-xs text-text-tertiary">{{ statusLabel }}</span>
          <button
            type="button"
            class="rounded-md border border-border px-2 py-1 text-xs text-text-secondary disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!store.canInterrupt"
            @click="store.interrupt()"
          >
            Stop
          </button>
        </div>
      </div>
    </header>

    <!-- Messages Area -->
    <main class="flex-1 overflow-y-auto p-4 md:p-8 scrollbar-thin scrollbar-thumb-border">
      <div class="max-w-4xl mx-auto pb-4">
        <div v-if="store.error" class="mb-3 rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
          {{ store.error }}
        </div>

        <div v-if="store.messages.length === 0" class="text-center py-20 text-text-tertiary">
          <p class="text-2xl font-bold mb-2 text-text-primary">Workspace Chat</p>
          <p v-if="store.currentConversationId === null">Select an agent and a conversation to start.</p>
          <p v-else>Send a message to start streaming.</p>
        </div>

        <MessageItem
          v-for="msg in store.messages"
          :key="msg.id"
          :message="msg"
          @submit-input="handleInputSubmit"
        />

        <div ref="messagesEndRef" class="h-1"></div>
      </div>
    </main>

    <!-- Input Area -->
    <footer class="flex-none p-4 md:p-6 bg-bg-secondary border-t border-border/50">
      <ChatInput
        :is-loading="store.isLoading"
        :disabled="store.currentConversationId === null"
        @submit="handleSubmit"
      />
    </footer>
  </div>
</template>
