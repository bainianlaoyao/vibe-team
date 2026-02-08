<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import {
  PhPaperPlaneRight,
  PhProhibitInset,
  PhSparkle,
  PhWifiHigh,
  PhWifiSlash,
} from '@phosphor-icons/vue';
import Avatar from '../components/Avatar.vue';
import { useAgentsStore } from '../stores/agents';
import { useConversationsStore } from '../stores/conversations';

const agentsStore = useAgentsStore();
const conversationsStore = useConversationsStore();
const activeAgentId = ref<string | null>(null);

const activeAgent = computed(() =>
  agentsStore.agents.find(agent => agent.id === activeAgentId.value) || agentsStore.agents[0] || null,
);
const wsConnected = computed(() => conversationsStore.socketState === 'connected');
const isSendingDisabled = computed(
  () => !conversationsStore.draft.trim() || !activeAgent.value || conversationsStore.loading,
);

onMounted(async () => {
  await agentsStore.fetchAgents();
  activeAgentId.value = agentsStore.agents[0]?.id || null;
  await conversationsStore.fetchConversations();
});

onBeforeUnmount(() => {
  conversationsStore.resetSocket();
});

const sendMessage = async () => {
  if (!activeAgent.value?.apiId) return;
  await conversationsStore.sendMessage(activeAgent.value.apiId);
};

const switchAgent = async (agentId: string) => {
  activeAgentId.value = agentId;
  if (conversationsStore.conversations.length > 0) {
    const conversation = conversationsStore.conversations.find(
      item => item.agentId === Number(agentId.replace('agent-', '')),
    );
    if (conversation) {
      await conversationsStore.setActiveConversation(conversation.id);
      return;
    }
  }
  conversationsStore.activeConversationId = null;
};
</script>

<template>
  <div class="flex-1 flex overflow-hidden h-full min-h-0">
    <aside class="w-72 border-r border-border bg-bg-tertiary flex flex-col h-full">
      <div class="p-4 border-b border-border">
        <div class="text-xs uppercase tracking-wide text-text-tertiary">Workspace Chat</div>
        <div class="text-sm font-semibold text-text-primary">Agents</div>
      </div>
      <div class="flex-1 overflow-auto px-3 py-2 space-y-1">
        <button
          v-for="agent in agentsStore.agents"
          :key="agent.id"
          class="w-full text-left px-3 py-2 rounded-md border transition-colors"
          :class="
            activeAgentId === agent.id
              ? 'bg-bg-elevated border-border shadow-soft'
              : 'border-transparent hover:bg-bg-elevated/70'
          "
          @click="switchAgent(agent.id)"
        >
          <div class="flex items-center gap-3">
            <Avatar
              :src="agent.avatar"
              :alt="agent.name"
              :fallback="agent.name[0]"
              container-class="w-9 h-9 rounded-full"
              text-class="text-sm"
              ring
              presence
              :presence-status="agent.status"
            />
            <div class="flex-1 min-w-0">
              <div class="text-sm font-semibold text-text-primary truncate">{{ agent.name }}</div>
              <div class="text-xs text-text-tertiary truncate">{{ agent.type }}</div>
            </div>
          </div>
        </button>
      </div>
    </aside>

    <div class="flex-1 flex flex-col bg-bg-secondary min-h-0">
      <div class="border-b border-border bg-bg-elevated px-6 py-3 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <Avatar
            :src="activeAgent?.avatar"
            :alt="activeAgent?.name"
            :fallback="activeAgent?.name?.[0] || 'A'"
            container-class="w-10 h-10 rounded-full"
            text-class="text-lg"
            ring
            :presence="Boolean(activeAgent)"
            :presence-status="activeAgent?.status || 'idle'"
          />
          <div>
            <div class="text-base font-semibold text-text-primary">{{ activeAgent?.name || 'No agent' }}</div>
            <div class="text-xs text-text-tertiary">
              {{ wsConnected ? 'WebSocket connected' : 'WebSocket reconnecting' }}
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <div class="flex items-center gap-1 text-xs text-text-tertiary">
            <PhWifiHigh v-if="wsConnected" :size="14" class="text-success" />
            <PhWifiSlash v-else :size="14" class="text-error" />
            <span>{{ conversationsStore.socketState }}</span>
          </div>
          <button
            class="flex items-center gap-2 text-sm px-3 py-1.5 bg-bg-tertiary border border-border rounded-md text-text-secondary hover:text-text-primary"
            @click="conversationsStore.interrupt()"
          >
            <PhProhibitInset :size="14" />
            Stop
          </button>
          <button class="flex items-center gap-2 text-sm px-3 py-1.5 bg-bg-tertiary border border-border rounded-md text-text-secondary hover:text-text-primary">
            <PhSparkle :size="14" />
            Auto-brief
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-auto px-6 py-5 space-y-4 bg-bg-elevated">
        <div v-if="conversationsStore.error" class="text-sm text-error">
          {{ conversationsStore.error }}
        </div>
        <div
          v-for="message in conversationsStore.activeMessages"
          :key="message.id"
          :class="['flex', message.role === 'user' ? 'justify-end' : 'justify-start']"
        >
          <div
            :class="[
              'max-w-[70%] rounded-lg px-4 py-3 text-xs shadow-soft',
              message.role === 'user'
                ? 'bg-brand text-white'
                : 'bg-bg-elevated border border-border text-text-primary',
            ]"
          >
            <div class="leading-relaxed whitespace-pre-wrap">{{ message.content }}</div>
            <div :class="['mt-2 text-xs', message.role === 'user' ? 'text-white/70' : 'text-text-tertiary']">
              {{ new Date(message.createdAt).toLocaleTimeString() }}
            </div>
          </div>
        </div>
        <div v-if="conversationsStore.streaming" class="flex items-center gap-2 text-xs text-text-tertiary">
          <span class="w-2 h-2 rounded-full bg-text-tertiary animate-pulse" />
          {{ activeAgent?.name }} is typing...
        </div>
      </div>

      <div class="border-t border-border bg-bg-elevated px-6 py-4">
        <form class="flex items-center gap-3" @submit.prevent="sendMessage">
          <div class="flex-1 bg-bg-tertiary border border-border rounded-md px-3 py-2">
            <textarea
              v-model="conversationsStore.draft"
              placeholder="Message your agent..."
              rows="1"
              class="w-full bg-transparent text-xs text-text-primary placeholder:text-text-tertiary focus:outline-none resize-none"
            />
          </div>
          <button
            type="submit"
            class="px-3 py-2 bg-brand text-white text-xs rounded-md flex items-center gap-2 disabled:opacity-50"
            :disabled="isSendingDisabled"
          >
            <PhPaperPlaneRight :size="14" />
            Send
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
