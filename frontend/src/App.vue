<script setup lang="ts">
import { computed, onErrorCaptured, ref } from 'vue';
import { useRoute } from 'vue-router';
import LeftSidebar from './components/layout/LeftSidebar.vue';
import TopNav from './components/layout/TopNav.vue';
import ProjectHeader from './components/layout/ProjectHeader.vue';
import ViewTabs from './components/layout/ViewTabs.vue';

const route = useRoute();

// Pages that show the project header and view tabs
const showProjectHeader = computed(() => {
  return route.path.startsWith('/agents');
});

// Pages that show the top nav
const showTopNav = computed(() => {
  return !showProjectHeader.value;
});

const fatalError = ref<string | null>(null);

onErrorCaptured(error => {
  fatalError.value = error instanceof Error ? error.message : String(error);
  return false;
});
</script>

<template>
  <div class="flex h-screen bg-bg-primary">
    <div
      v-if="fatalError"
      class="fixed inset-x-4 top-4 z-50 rounded-md border border-error/40 bg-error/10 px-4 py-3 text-xs text-error"
      role="alert"
    >
      {{ fatalError }}
    </div>
    <LeftSidebar />
    <div class="flex-1 flex flex-col overflow-hidden">
      <TopNav v-if="showTopNav" />
      <template v-if="showProjectHeader">
        <ProjectHeader />
        <ViewTabs />
      </template>
      <main class="flex-1 overflow-auto">
        <router-view />
      </main>
    </div>
  </div>
</template>
