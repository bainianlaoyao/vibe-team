<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  PhArrowLeft,
  PhCaretRight,
  PhFileCode,
  PhFileCsv,
  PhFileText,
  PhFolder,
  PhHardDrive,
  PhImage,
  PhLock,
  PhMagnifyingGlass,
  PhPlus,
  PhStar,
} from '@phosphor-icons/vue';
import { useAgentsStore } from '../stores/agents';
import { useFileSystemStore } from '../stores/fileSystem';
import type { FileNode, PermissionLevel } from '../types';
import Avatar from '../components/Avatar.vue';

const router = useRouter();
const fileStore = useFileSystemStore();
const agentsStore = useAgentsStore();

const path = ref<FileNode[]>([]);
const searchTerm = ref('');
const permissionFilter = ref<PermissionLevel | 'all'>('all');

const getIconForItem = (item: FileNode) => {
  if (item.type === 'folder') return PhFolder;
  const name = item.name.toLowerCase();
  if (name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg')) return PhImage;
  if (name.endsWith('.csv') || name.endsWith('.xls')) return PhFileCsv;
  if (name.endsWith('.ts') || name.endsWith('.tsx') || name.endsWith('.js') || name.endsWith('.vue')) return PhFileCode;
  return PhFileText;
};

const currentFolder = computed(() => path.value[path.value.length - 1] || fileStore.root);
const items = computed(() => currentFolder.value?.children || []);

const filteredItems = computed(() => {
  const keyword = searchTerm.value.trim().toLowerCase();
  if (!keyword) return items.value;
  return items.value.filter(item => item.name.toLowerCase().includes(keyword));
});

const visibleItems = computed(() => {
  if (permissionFilter.value === 'all') return filteredItems.value;
  return filteredItems.value.filter(item => item.permission === permissionFilter.value);
});

const permissionLabel: Record<PermissionLevel, string> = {
  read: 'Readable',
  write: 'Writable',
  none: 'No access',
};

const getOwnerAgent = (owner: string) => {
  const normalized = owner.toLowerCase();
  return agentsStore.agents.find(agent => agent.name.toLowerCase() === normalized) || null;
};

const openFolder = (folder: FileNode) => {
  if (folder.type !== 'folder') return;
  path.value = [...path.value, folder];
};

const openItem = (item: FileNode) => {
  if (item.type === 'folder') {
    openFolder(item);
    return;
  }
  router.push(`/files/view/${encodeURIComponent(item.id)}`);
};

const goToCrumb = (index: number) => {
  path.value = path.value.slice(0, index + 1);
};

const goUp = () => {
  if (path.value.length > 1) {
    path.value = path.value.slice(0, path.value.length - 1);
  }
};

const setPermission = async (item: FileNode, level: PermissionLevel | 'inherit') => {
  await fileStore.setPermission(item.id, level);
};

onMounted(async () => {
  await Promise.all([fileStore.fetchTree('.', 5), agentsStore.fetchAgents()]);
  if (fileStore.root) {
    path.value = [fileStore.root];
  }
});
</script>

<template>
  <div class="flex-1 flex overflow-hidden h-full min-h-0">
    <aside class="w-64 border-r border-border bg-bg-tertiary px-3 py-4 space-y-5 h-full">
      <div>
        <div class="text-sm uppercase tracking-wide text-text-secondary mb-3 font-semibold">Favorites</div>
        <div class="space-y-2 text-sm">
          <button class="w-full flex items-center gap-2 px-3 py-2 rounded-md bg-bg-elevated border border-border text-text-primary">
            <PhStar :size="14" />
            Project Files
          </button>
          <button class="w-full flex items-center gap-2 px-3 py-2 rounded-md text-text-secondary hover:bg-bg-elevated/70">
            <PhHardDrive :size="14" />
            Storage
          </button>
        </div>
      </div>
      <div>
        <div class="text-sm uppercase tracking-wide text-text-secondary mb-3 font-semibold">Pinned</div>
        <div class="space-y-2 text-sm">
          <button
            v-for="folder in fileStore.rootChildren.filter(child => child.type === 'folder')"
            :key="folder.id"
            class="w-full flex items-center gap-2 px-3 py-2 rounded-md text-text-secondary hover:bg-bg-elevated/70"
            @click="openFolder(folder)"
          >
            <PhFolder :size="14" />
            {{ folder.name }}
          </button>
        </div>
      </div>
    </aside>

    <div class="flex-1 flex flex-col overflow-hidden min-h-0">
      <div class="border-b border-border bg-bg-elevated px-5 py-3 flex items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <button
            class="p-2 rounded-md bg-bg-tertiary border border-border text-text-secondary hover:text-text-primary disabled:opacity-40"
            :disabled="path.length <= 1"
            aria-label="Go up"
            @click="goUp"
          >
            <PhArrowLeft :size="14" />
          </button>
          <div class="flex items-center text-sm text-text-secondary">
            <div v-for="(crumb, index) in path" :key="crumb.id" class="flex items-center">
              <button class="hover:text-text-primary" @click="goToCrumb(index)">
                {{ crumb.name }}
              </button>
              <PhCaretRight v-if="index < path.length - 1" :size="14" class="mx-2 text-text-tertiary" />
            </div>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <div class="flex items-center gap-2 bg-bg-tertiary border border-border rounded-md px-3 py-2">
            <PhMagnifyingGlass :size="14" class="text-text-tertiary" />
            <input
              v-model="searchTerm"
              class="w-40 bg-transparent text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none"
              placeholder="Search folder"
            />
          </div>
          <select
            v-model="permissionFilter"
            class="px-3 py-2 text-sm border border-border rounded bg-bg-tertiary text-text-secondary"
          >
            <option value="all">Agent access: All</option>
            <option value="read">Agent access: Readable</option>
            <option value="write">Agent access: Writable</option>
            <option value="none">Agent access: No access</option>
          </select>
          <button class="flex items-center gap-2 text-sm px-3 py-2 bg-bg-tertiary border border-border rounded-md text-text-secondary hover:text-text-primary">
            <PhPlus :size="14" />
            New folder
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-auto p-6 bg-bg-elevated">
        <div v-if="fileStore.loading" class="text-sm text-text-tertiary">Loading files...</div>
        <div v-else-if="fileStore.error" class="text-sm text-error">{{ fileStore.error }}</div>
        <template v-else>
          <div class="grid grid-cols-[minmax(0,1fr)_140px_140px_160px_170px] text-sm uppercase tracking-wide text-text-tertiary pb-2 border-b border-border">
            <div>Name</div>
            <div>Kind</div>
            <div>Modified</div>
            <div>Owner</div>
            <div>Agent access</div>
          </div>
          <div class="divide-y divide-border">
            <button
              v-for="item in visibleItems"
              :key="item.id"
              class="w-full grid grid-cols-[minmax(0,1fr)_140px_140px_160px_170px] text-left text-sm text-text-primary py-3 hover:bg-bg-tertiary"
              @click="openItem(item)"
            >
              <div class="flex items-center gap-3">
                <component :is="getIconForItem(item)" :size="16" class="text-text-tertiary" />
                <span class="truncate">{{ item.name }}</span>
                <span v-if="item.permission === 'none'" class="text-text-tertiary" title="Agents cannot access">
                  <PhLock :size="12" />
                </span>
              </div>
              <div class="text-text-secondary">{{ item.kind }}</div>
              <div class="text-text-secondary">
                {{ item.modifiedAt ? new Date(item.modifiedAt).toLocaleDateString() : '--' }}
              </div>
              <div class="flex items-center gap-2 text-text-secondary">
                <template v-if="getOwnerAgent(item.owner)">
                  <Avatar
                    :src="getOwnerAgent(item.owner)?.avatar"
                    :alt="getOwnerAgent(item.owner)?.name"
                    :fallback="getOwnerAgent(item.owner)?.name?.[0] || 'A'"
                    container-class="w-7 h-7 rounded-full"
                    text-class="text-sm"
                  />
                  <span class="text-text-primary">{{ getOwnerAgent(item.owner)?.name }}</span>
                </template>
                <span v-else>{{ item.owner }}</span>
              </div>
              <div class="text-text-secondary" @click.stop>
                <select
                  :value="item.permission"
                  class="w-full px-2 py-1 text-sm border border-border rounded bg-bg-tertiary text-text-secondary"
                  @change="setPermission(item, ($event.target as HTMLSelectElement).value as PermissionLevel | 'inherit')"
                >
                  <option :value="item.permission">{{ permissionLabel[item.permission] }}</option>
                  <option value="read">Readable</option>
                  <option value="write">Writable</option>
                  <option value="none">No access</option>
                  <option value="inherit">Inherit</option>
                </select>
              </div>
            </button>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
