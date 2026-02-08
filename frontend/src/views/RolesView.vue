<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { PhCheck, PhCopy, PhFileText, PhPencil, PhPlus, PhTrash, PhX } from '@phosphor-icons/vue';
import Avatar from '../components/Avatar.vue';
import { useRolesStore } from '../stores/roles';
import type { RoleProfile } from '../types';

const rolesStore = useRolesStore();
const drawerOpen = ref(false);
const editingId = ref<string | null>(null);
const draft = ref({ name: '', description: '', checkpointPreference: '', tags: '' });

const resetDraft = () => {
  draft.value = { name: '', description: '', checkpointPreference: '', tags: '' };
  editingId.value = null;
  drawerOpen.value = false;
};

const openNewRole = () => {
  editingId.value = null;
  draft.value = { name: '', description: '', checkpointPreference: '', tags: '' };
  drawerOpen.value = true;
};

const startEdit = (profile: RoleProfile) => {
  editingId.value = profile.id;
  draft.value = {
    name: profile.name,
    description: profile.description,
    checkpointPreference: profile.checkpointPreference,
    tags: profile.tags.join(', '),
  };
  drawerOpen.value = true;
};

const duplicateProfile = async (profile: RoleProfile) => {
  await rolesStore.createRole({
    name: `${profile.name} Copy`,
    description: profile.description,
    checkpointPreference: profile.checkpointPreference,
    tags: [...profile.tags],
  });
};

const handleSubmit = async () => {
  if (!draft.value.name.trim()) return;
  const nextTags = draft.value.tags
    .split(',')
    .map(tag => tag.trim())
    .filter(Boolean);
  if (editingId.value) {
    await rolesStore.updateRole({
      id: editingId.value,
      name: draft.value.name.trim(),
      description: draft.value.description.trim(),
      checkpointPreference: draft.value.checkpointPreference.trim(),
      tags: nextTags,
    });
  } else {
    await rolesStore.createRole({
      name: draft.value.name.trim(),
      description: draft.value.description.trim(),
      checkpointPreference: draft.value.checkpointPreference.trim(),
      tags: nextTags,
    });
  }
  resetDraft();
};

onMounted(async () => {
  await rolesStore.fetchRoles();
});
</script>

<template>
  <div class="flex-1 overflow-auto p-6 space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-lg font-semibold text-text-primary">Role Profiles</h2>
      </div>
      <div class="flex items-center gap-3">
        <div class="text-xs text-text-tertiary">{{ rolesStore.roles.length }} profiles</div>
        <button
          class="flex items-center gap-2 text-xs px-3 py-2 bg-brand hover:bg-brand/90 text-white rounded-md"
          @click="openNewRole"
        >
          <PhPlus :size="14" />
          New role profile
        </button>
      </div>
    </div>

    <div v-if="rolesStore.loading" class="text-sm text-text-tertiary">Loading roles...</div>
    <div v-else-if="rolesStore.error" class="text-sm text-error">{{ rolesStore.error }}</div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      <div
        v-for="profile in rolesStore.roles"
        :key="profile.id"
        class="border border-border rounded-lg p-4 bg-bg-elevated flex flex-col cursor-pointer hover:shadow-soft transition-shadow"
      >
        <div class="flex items-start justify-between gap-4">
          <div class="flex items-start gap-3">
            <Avatar
              alt="role"
              fallback="R"
              container-class="w-12 h-12 rounded-full shadow-[0_10px_18px_rgba(40,35,28,0.16)]"
              text-class="text-base"
              ring
            />
            <div>
              <div class="flex items-center gap-2">
                <div class="text-sm font-semibold text-text-primary">{{ profile.name }}</div>
                <PhFileText :size="14" class="text-text-tertiary" />
              </div>
              <div class="text-sm text-text-secondary mt-2">Goal: {{ profile.description }}</div>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button
              class="p-2 rounded-md border border-border bg-bg-tertiary text-text-secondary hover:text-text-primary"
              aria-label="Edit role"
              @click.stop="startEdit(profile)"
            >
              <PhPencil :size="14" />
            </button>
            <button
              class="p-2 rounded-md border border-border bg-bg-tertiary text-text-secondary hover:text-text-primary"
              aria-label="Duplicate role"
              @click.stop="duplicateProfile(profile)"
            >
              <PhCopy :size="14" />
            </button>
            <button
              class="p-2 rounded-md border border-border bg-bg-tertiary text-text-secondary hover:text-error"
              aria-label="Delete role"
              @click.stop="rolesStore.deleteRole(profile.id)"
            >
              <PhTrash :size="14" />
            </button>
          </div>
        </div>
        <div class="mt-3 text-sm text-text-tertiary">
          Checkpoints: {{ profile.checkpointPreference || 'No preference set' }}
        </div>
        <div class="mt-2 flex flex-wrap gap-1">
          <span v-for="tag in profile.tags" :key="tag" class="text-xs px-2 py-0.5 bg-bg-tertiary border border-border rounded-full text-text-secondary">
            {{ tag }}
          </span>
        </div>
      </div>
    </div>

    <div v-if="drawerOpen" class="fixed inset-0 z-50 flex">
      <div class="flex-1 bg-black/20" aria-hidden="true" @click="resetDraft" />
      <div class="w-full max-w-xl bg-bg-elevated border-l border-border h-full overflow-auto">
        <div class="px-6 py-5 border-b border-border flex items-center justify-between">
          <div>
            <h3 class="text-sm font-semibold text-text-primary">
              {{ editingId ? 'Edit Role Profile' : 'New Role Profile' }}
            </h3>
            <div class="text-xs text-text-tertiary mt-1">Define how the agent should operate and learn.</div>
          </div>
          <button
            type="button"
            class="p-2 rounded-md border border-border bg-bg-tertiary text-text-secondary hover:text-text-primary"
            @click="resetDraft"
          >
            <PhX :size="14" />
          </button>
        </div>

        <form class="px-6 py-5 space-y-4" @submit.prevent="handleSubmit">
          <div class="space-y-1">
            <label class="text-xs text-text-tertiary uppercase tracking-wide">Role name</label>
            <input
              v-model="draft.name"
              class="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-xs text-text-primary"
              placeholder="e.g. QA Automation"
            />
          </div>
          <div class="space-y-1">
            <label class="text-xs text-text-tertiary uppercase tracking-wide">Description</label>
            <textarea
              v-model="draft.description"
              class="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-xs text-text-primary h-24 resize-none"
              placeholder="Describe responsibilities, scope, and expectations."
            />
          </div>
          <div class="space-y-1">
            <label class="text-xs text-text-tertiary uppercase tracking-wide">Human checkpoint preference</label>
            <input
              v-model="draft.checkpointPreference"
              class="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-xs text-text-primary"
              placeholder="e.g. Ask before final output and after first draft"
            />
          </div>
          <div class="space-y-1">
            <label class="text-xs text-text-tertiary uppercase tracking-wide">Tags</label>
            <input
              v-model="draft.tags"
              class="w-full bg-bg-tertiary border border-border rounded-md px-3 py-2 text-xs text-text-primary"
              placeholder="Comma separated tags"
            />
          </div>
          <button
            type="submit"
            class="w-full px-4 py-2 text-xs bg-brand hover:bg-brand/90 text-white rounded-md flex items-center justify-center gap-2"
          >
            <PhCheck v-if="editingId" :size="14" />
            <PhPlus v-else :size="14" />
            {{ editingId ? 'Save role profile' : 'Create role profile' }}
          </button>
        </form>
      </div>
    </div>
  </div>
</template>
