<script setup lang="ts">
import { PhSliders, PhSquaresFour, PhTable } from '@phosphor-icons/vue';
</script>

<template>
  <div class="flex-1 overflow-auto p-6">
    <div class="bg-bg-elevated border border-border rounded-lg p-6">
      <div class="flex items-center gap-2 mb-4">
        <PhSliders :size="16" class="text-text-tertiary" />
        <h3 class="text-sm font-semibold text-text-primary">Customize Agent Views</h3>
      </div>
      <p class="text-sm text-text-secondary mb-6">
        Create tailored views for each team. Choose the fields and filters that matter most.
      </p>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="border border-border rounded-md p-4 bg-bg-tertiary">
          <div class="flex items-center gap-2 text-sm font-medium text-text-primary mb-2">
            <PhSquaresFour :size="16" />
            Kanban configuration
          </div>
          <p class="text-xs text-text-tertiary">
            Set default columns, WIP limits, and card density.
          </p>
        </div>
        <div class="border border-border rounded-md p-4 bg-bg-tertiary">
          <div class="flex items-center gap-2 text-sm font-medium text-text-primary mb-2">
            <PhTable :size="16" />
            Table configuration
          </div>
          <p class="text-xs text-text-tertiary">
            Choose visible columns and default sorting.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>
