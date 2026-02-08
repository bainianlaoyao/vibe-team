<script setup lang="ts">
import { computed } from 'vue';
import type { AgentStatus } from '../types';

const props = withDefaults(defineProps<{
  src?: string;
  alt?: string;
  fallback?: string;
  containerClass?: string;
  textClass?: string;
  ring?: boolean;
  presence?: boolean;
  presenceStatus?: AgentStatus;
}>(), {
  fallback: 'A',
  containerClass: '',
  textClass: '',
  ring: false,
  presence: false,
  presenceStatus: 'idle',
});

const hasImage = computed(() => Boolean(props.src && props.src.startsWith('/')));

const presenceColor = computed(() => {
  switch (props.presenceStatus) {
    case 'active':
      return 'bg-success';
    case 'busy':
      return 'bg-warning';
    case 'blocked':
      return 'bg-error';
    default:
      return 'bg-primary-400';
  }
});
</script>

<template>
  <div class="relative inline-block">
    <div
      :class="[
        'flex items-center justify-center bg-bg-tertiary border border-border overflow-hidden',
        ring ? 'ring-2 ring-white ring-offset-1' : '',
        containerClass,
      ]"
    >
      <img
        v-if="hasImage"
        :src="src"
        :alt="alt"
        class="w-full h-full object-cover"
      />
      <span
        v-else
        :class="['font-semibold text-text-secondary', textClass]"
      >
        {{ fallback }}
      </span>
    </div>
    <span
      v-if="presence"
      :class="[
        'absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-white',
        presenceColor,
      ]"
    />
  </div>
</template>
