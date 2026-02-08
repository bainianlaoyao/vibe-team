<script setup lang="ts">
import {
  PhMagnifyingGlass,
  PhBell,
  PhGear,
} from '@phosphor-icons/vue';
import Avatar from '../Avatar.vue';
</script>

<template>
  <header class="h-14 bg-bg-elevated border-b border-border px-6 flex items-center justify-between">
    <!-- Search -->
    <div class="flex items-center gap-3 flex-1 max-w-md">
      <div class="flex items-center gap-2 bg-bg-tertiary border border-border rounded-lg px-3 py-2 flex-1">
        <PhMagnifyingGlass :size="16" class="text-text-tertiary" />
        <input
          id="global-search-input"
          type="text"
          name="global_search"
          placeholder="Search tasks, agents, files..."
          class="w-full bg-transparent text-sm text-text-primary placeholder:text-text-tertiary focus:outline-none"
        />
        <kbd class="hidden sm:inline-block text-xs text-text-tertiary bg-bg-elevated border border-border rounded px-1.5 py-0.5">
          ⌘K
        </kbd>
      </div>
    </div>

    <!-- Actions -->
    <div class="flex items-center gap-3">
      <button
        class="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        aria-label="Notifications"
      >
        <PhBell :size="20" />
      </button>
      <button
        class="p-2 rounded-lg text-text-secondary hover:text-text-primary hover:bg-bg-tertiary transition-colors"
        aria-label="Settings"
      >
        <PhGear :size="20" />
      </button>
      <div class="w-px h-6 bg-border mx-1" />
      <Avatar
        src="/avatars/user.png"
        alt="User"
        fallback="U"
        class="w-8 h-8 rounded-full cursor-pointer"
        text-class="text-sm"
      />
    </div>
  </header>
</template>
