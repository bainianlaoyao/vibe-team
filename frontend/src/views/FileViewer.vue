<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import {
  PhArrowLeft,
  PhDownloadSimple,
  PhImage,
  PhLock,
  PhShareNetwork,
} from '@phosphor-icons/vue';
import { useFileSystemStore } from '../stores/fileSystem';
import type { PermissionLevel } from '../types';

type PreviewType = 'markdown' | 'code' | 'image' | 'csv' | 'text';

const router = useRouter();
const route = useRoute();
const fileStore = useFileSystemStore();
const fileContent = ref<string | null>(null);
const loading = ref(false);

const id = computed(() => decodeURIComponent(String(route.params.id || '')));
const file = computed(() => fileStore.findNodeById(id.value));
const path = computed(() => fileStore.findPathToId(id.value));

const getPreviewType = (name: string): PreviewType => {
  const lower = name.toLowerCase();
  if (lower.endsWith('.md')) return 'markdown';
  if (lower.endsWith('.ts') || lower.endsWith('.tsx') || lower.endsWith('.js') || lower.endsWith('.vue')) return 'code';
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image';
  if (lower.endsWith('.csv')) return 'csv';
  return 'text';
};

const permissionLabel: Record<PermissionLevel, string> = {
  read: 'Readable',
  write: 'Writable',
  none: 'No access',
};

const previewType = computed(() => (file.value ? getPreviewType(file.value.name) : 'text'));
const effectivePermission = computed(() =>
  path.value ? fileStore.getEffectivePermissionForPath(path.value) : 'read',
);
const pathLabel = computed(() => path.value?.map(node => node.name).join(' / ') || '');

const parseCsv = (content: string) => {
  const rows = content
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => line.split(','));
  if (rows.length === 0) return { headers: [] as string[], rows: [] as string[][] };
  const [headers, ...dataRows] = rows;
  return { headers, rows: dataRows };
};

const loadContent = async () => {
  if (!file.value || file.value.type !== 'file') {
    fileContent.value = null;
    return;
  }
  if (previewType.value === 'image') {
    fileContent.value = null;
    return;
  }
  loading.value = true;
  fileContent.value = await fileStore.getFileContent(file.value.id);
  loading.value = false;
};

watch(id, async () => {
  await loadContent();
});

onMounted(async () => {
  if (!fileStore.root) {
    await fileStore.fetchTree('.', 5);
  }
  await loadContent();
});
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden min-h-0 bg-bg-secondary">
    <template v-if="!file || !path">
      <div class="flex-1 p-6">
        <button
          class="text-xs px-3 py-2 bg-bg-tertiary border border-border rounded-md text-text-secondary hover:text-text-primary"
          @click="router.push('/files')"
        >
          Back to files
        </button>
        <div class="mt-6 text-sm text-text-tertiary">File not found.</div>
      </div>
    </template>

    <template v-else-if="file.type === 'folder'">
      <div class="flex-1 p-6">
        <button
          class="text-xs px-3 py-2 bg-bg-tertiary border border-border rounded-md text-text-secondary hover:text-text-primary"
          @click="router.push('/files')"
        >
          Back to files
        </button>
        <div class="mt-6 text-sm text-text-tertiary">This item is a folder.</div>
      </div>
    </template>

    <template v-else>
      <div class="sticky top-0 z-10 border-b border-border bg-bg-elevated/95 backdrop-blur px-6 py-4 flex items-center justify-between gap-4">
        <div class="flex items-center gap-3 min-w-0">
          <button
            class="p-2 rounded-md bg-bg-tertiary border border-border text-text-secondary hover:text-text-primary"
            aria-label="Back to files"
            @click="router.back()"
          >
            <PhArrowLeft :size="14" />
          </button>
          <div class="min-w-0">
            <div class="text-sm font-semibold text-text-primary truncate">{{ file.name }}</div>
            <div class="text-xs text-text-tertiary truncate">{{ pathLabel }}</div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button class="flex items-center gap-2 text-xs px-3 py-2 bg-brand hover:bg-brand/90 text-white rounded-md">
            <PhShareNetwork :size="14" />
            Share
          </button>
          <button class="flex items-center gap-2 text-xs px-3 py-2 bg-bg-tertiary border border-border rounded-md text-text-secondary hover:text-text-primary">
            <PhDownloadSimple :size="14" />
            Download
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-auto">
        <div class="mx-auto w-full px-6 py-8">
          <div class="space-y-4">
            <div class="flex flex-wrap items-center gap-2 text-xs text-text-secondary">
              <span class="px-2 py-1 rounded-full bg-bg-tertiary border border-border">{{ file.kind }}</span>
              <span class="px-2 py-1 rounded-full bg-bg-tertiary border border-border">
                {{ file.modifiedAt ? new Date(file.modifiedAt).toLocaleString() : '--' }}
              </span>
              <span class="px-2 py-1 rounded-full bg-bg-tertiary border border-border">
                Owner: {{ file.owner || '—' }}
              </span>
            </div>

            <div
              v-if="effectivePermission === 'none'"
              class="flex items-center gap-2 text-xs text-text-tertiary bg-bg-tertiary border border-border rounded-md px-3 py-2"
            >
              <PhLock :size="12" />
              Agents cannot access this file.
            </div>

            <div v-if="loading" class="text-sm text-text-tertiary">Loading content...</div>
            <div v-else-if="previewType === 'image'" class="bg-bg-elevated border border-border rounded-[28px] shadow-soft p-12 min-h-[60vh]">
              <div class="text-center space-y-3">
                <div class="w-56 h-36 rounded-xl bg-gradient-to-br from-primary-200 via-primary-100 to-primary-50 flex items-center justify-center border border-border mx-auto">
                  <PhImage :size="28" class="text-text-tertiary" />
                </div>
                <div class="text-xs text-text-tertiary">Binary image preview not rendered in MVP.</div>
              </div>
            </div>
            <div v-else-if="previewType === 'csv'" class="bg-bg-elevated border border-border rounded-[28px] shadow-soft p-6 min-h-[60vh]">
              <div class="rounded-xl border border-border overflow-hidden">
                <table class="w-full text-xs">
                  <thead class="bg-bg-tertiary">
                    <tr>
                      <th v-for="(header, index) in parseCsv(fileContent || '').headers" :key="index" class="px-4 py-2 text-left text-text-tertiary">
                        {{ header }}
                      </th>
                    </tr>
                  </thead>
                  <tbody class="bg-bg-elevated">
                    <tr v-for="(row, rowIndex) in parseCsv(fileContent || '').rows" :key="rowIndex" class="border-t border-border">
                      <td v-for="(cell, cellIndex) in row" :key="cellIndex" class="px-4 py-2 text-text-secondary">
                        {{ cell }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            <div v-else class="bg-bg-elevated border border-border rounded-[28px] shadow-soft p-12 min-h-[60vh]">
              <pre class="text-sm text-text-secondary leading-7 whitespace-pre-wrap">{{ fileContent || 'No preview content available.' }}</pre>
            </div>

            <div class="bg-bg-elevated border border-border rounded-lg p-4">
              <div class="text-xs uppercase tracking-wide text-text-tertiary mb-3">Agent access</div>
              <div class="flex items-center gap-2">
                <span class="text-sm font-semibold text-text-primary">{{ permissionLabel[effectivePermission] }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
