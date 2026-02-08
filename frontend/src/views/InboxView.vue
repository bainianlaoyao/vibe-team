<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { PhCheck, PhDotsThree, PhEnvelope, PhTrash } from '@phosphor-icons/vue';
import { useInboxStore } from '../stores/inbox';

const inboxStore = useInboxStore();
const userInput = ref<string>('');

onMounted(async () => {
  await inboxStore.fetchInbox();
});

const selectItem = async (id: string) => {
  inboxStore.selectedId = id;
  const item = inboxStore.items.find(entry => entry.id === id);
  if (item && !item.read) {
    await inboxStore.markAsRead(item);
  }
};

const closeSelected = async () => {
  if (!inboxStore.selectedItem) return;
  const input = userInput.value.trim() || undefined;
  await inboxStore.closeItem(inboxStore.selectedItem, input);
  userInput.value = '';
};
</script>

<template>
  <div class="flex-1 flex overflow-hidden">
    <div class="w-96 border-r border-border bg-bg-tertiary overflow-auto">
      <div class="p-4 border-b border-border">
        <h2 class="text-lg font-semibold text-text-primary">Inbox</h2>
        <div class="text-sm text-text-tertiary">{{ inboxStore.unreadCount }} unread</div>
      </div>
      <div v-if="inboxStore.loading" class="p-4 text-sm text-text-tertiary">Loading inbox...</div>
      <div v-else-if="inboxStore.error" class="p-4 text-sm text-error">{{ inboxStore.error }}</div>
      <div v-else class="divide-y divide-border">
        <div
          v-for="item in inboxStore.items"
          :key="item.id"
          class="p-4 cursor-pointer hover:bg-bg-elevated transition-colors"
          :class="{ 'bg-bg-elevated': inboxStore.selectedId === item.id }"
          @click="selectItem(item.id)"
        >
          <div class="flex items-start gap-3">
            <div class="w-2 h-2 rounded-full mt-2 flex-shrink-0" :class="item.read ? 'bg-transparent' : 'bg-brand'" />
            <div class="flex-1 min-w-0">
              <div class="flex items-center justify-between gap-2">
                <span class="text-sm font-semibold text-text-primary truncate">{{ item.subject }}</span>
                <span class="text-xs text-text-tertiary flex-shrink-0">{{ item.time }}</span>
              </div>
              <div class="text-xs text-text-tertiary mt-0.5">{{ item.from }}</div>
              <div class="text-sm text-text-secondary mt-1 line-clamp-2">{{ item.preview }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="flex-1 bg-bg-elevated overflow-auto">
      <template v-if="inboxStore.selectedItem">
        <div class="p-6">
          <div class="flex items-start justify-between mb-6">
            <div>
              <h1 class="text-xl font-semibold text-text-primary">{{ inboxStore.selectedItem.subject }}</h1>
              <div class="text-sm text-text-tertiary mt-1">
                From: {{ inboxStore.selectedItem.from }} · {{ inboxStore.selectedItem.time }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="p-2 rounded-lg hover:bg-bg-tertiary text-text-secondary"
                aria-label="Close inbox item"
                @click="closeSelected"
              >
                <PhCheck :size="18" />
              </button>
              <button
                class="p-2 rounded-lg hover:bg-bg-tertiary text-text-secondary"
                aria-label="Delete inbox item"
                @click="closeSelected"
              >
                <PhTrash :size="18" />
              </button>
              <button class="p-2 rounded-lg hover:bg-bg-tertiary text-text-secondary" aria-label="More inbox actions">
                <PhDotsThree :size="18" />
              </button>
            </div>
          </div>
          <div class="prose prose-sm text-text-secondary">
            <p>{{ inboxStore.selectedItem.preview }}</p>
          </div>
          <div class="mt-4">
            <label class="text-xs text-text-tertiary uppercase tracking-wide">User Input (optional)</label>
            <textarea
              id="inbox-user-input"
              v-model="userInput"
              name="user_input"
              class="mt-2 w-full min-h-24 bg-bg-tertiary border border-border rounded-md px-3 py-2 text-sm text-text-primary"
              placeholder="Provide response before closing if needed..."
            />
            <button
              class="mt-3 px-3 py-2 text-xs bg-brand hover:bg-brand/90 text-white rounded-md"
              @click="closeSelected"
            >
              Close Item
            </button>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="flex items-center justify-center h-full text-text-tertiary">
          <div class="text-center">
            <PhEnvelope :size="48" class="mx-auto mb-3 opacity-50" />
            <p>Select a message to view</p>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
