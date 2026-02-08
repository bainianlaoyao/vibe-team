import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { ApiRequestError, api } from '../services/api';
import type { InboxItem } from '../types';

function formatRelativeTime(timestamp: string): string {
  const now = Date.now();
  const target = new Date(timestamp).getTime();
  const diffMs = Math.max(0, now - target);
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffHours < 1) return 'just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export const useInboxStore = defineStore('inbox', () => {
  const projectId = ref<number>(api.getProjectId());
  const items = ref<InboxItem[]>([]);
  const selectedId = ref<string | null>(null);
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  const unreadCount = computed(() => items.value.filter(item => !item.read).length);
  const selectedItem = computed(() => items.value.find(item => item.id === selectedId.value) || null);

  async function fetchInbox(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const rows = await api.listInbox(projectId.value);
      items.value = rows.map(row => ({
        id: `inbox-${row.id}`,
        apiId: row.id,
        subject: row.title,
        preview: row.content,
        from: row.resolver || row.source_type,
        time: formatRelativeTime(row.created_at),
        read: row.is_read,
        status: row.status,
      }));
      if (selectedId.value === null && items.value.length > 0) {
        selectedId.value = items.value[0]?.id || null;
      }
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to load inbox.';
    } finally {
      loading.value = false;
    }
  }

  async function markAsRead(item: InboxItem): Promise<void> {
    try {
      await api.markInboxRead(item.apiId);
      item.read = true;
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to mark inbox item as read.';
    }
  }

  async function closeItem(item: InboxItem, userInput?: string): Promise<void> {
    try {
      await api.closeInboxItem(item.apiId, userInput);
      await fetchInbox();
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to close inbox item.';
    }
  }

  return {
    projectId,
    items,
    selectedId,
    selectedItem,
    unreadCount,
    loading,
    error,
    fetchInbox,
    markAsRead,
    closeItem,
  };
});
