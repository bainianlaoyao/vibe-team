<script setup lang="ts">
import { computed, onMounted } from 'vue';
import { PhTrendUp, PhWarningCircle } from '@phosphor-icons/vue';
import { useUsageStore } from '../stores/usage';

const usageStore = useUsageStore();

const totalRequests = computed(() =>
  usageStore.timeline.reduce((sum, point) => sum + point.totalRequestCount, 0),
);

const modelMix = computed(() => {
  const bucket: Record<string, number> = {};
  for (const point of usageStore.timeline) {
    for (const [provider, entry] of Object.entries(point.providers)) {
      bucket[provider] = (bucket[provider] || 0) + entry.costUsd;
    }
  }
  return Object.entries(bucket).sort((a, b) => b[1] - a[1]);
});

const maxRequests = computed(() =>
  Math.max(1, ...usageStore.timeline.map(point => point.totalRequestCount)),
);

onMounted(async () => {
  await usageStore.fetchUsage(30);
});
</script>

<template>
  <div class="flex-1 overflow-auto p-6">
    <div class="flex flex-col gap-4 md:flex-row md:items-center md:justify-between mb-6">
      <div>
        <h2 class="text-lg font-semibold text-text-primary">API Usage Ledger</h2>
        <div class="text-sm text-text-tertiary mt-1">Live data from backend usage and error endpoints.</div>
      </div>
      <button class="px-3.5 py-2 text-xs bg-brand hover:bg-brand/90 text-white rounded-md transition-colors" @click="usageStore.fetchUsage(30)">
        Refresh
      </button>
    </div>

    <div v-if="usageStore.loading" class="text-sm text-text-tertiary">Loading usage metrics...</div>
    <div v-else-if="usageStore.error" class="text-sm text-error">{{ usageStore.error }}</div>
    <div v-else class="grid grid-cols-1 gap-6 xl:grid-cols-[260px_minmax(0,1fr)] 2xl:grid-cols-[260px_minmax(0,1fr)_320px]">
      <div class="space-y-6">
        <div class="bg-bg-elevated border border-border rounded-lg p-5 shadow-soft">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-text-primary uppercase tracking-wide">Budget Window</h3>
            <span class="text-xs text-text-tertiary">
              ${{ usageStore.budget?.budgetUsd.toFixed(2) || '0.00' }}/month
            </span>
          </div>
          <div class="space-y-3">
            <div class="flex items-baseline justify-between">
              <span class="text-xs text-text-tertiary">Total spend</span>
              <span class="text-lg font-semibold text-text-primary">${{ usageStore.budget?.usedUsd.toFixed(2) || '0.00' }}</span>
            </div>
            <div class="w-full h-2 bg-primary-200 rounded-full overflow-hidden">
              <div
                class="h-full bg-brand transition-all"
                :style="{ width: `${Math.min(100, (usageStore.budget?.utilizationRatio || 0) * 100)}%` }"
              />
            </div>
            <div class="flex flex-wrap gap-2 text-xs text-text-secondary">
              <span class="px-2 py-1 bg-bg-tertiary border border-border rounded-full">
                {{ ((usageStore.budget?.utilizationRatio || 0) * 100).toFixed(0) }}% used
              </span>
              <span class="px-2 py-1 bg-bg-tertiary border border-border rounded-full">
                ${{ usageStore.budget?.remainingUsd.toFixed(2) || '0.00' }} left
              </span>
            </div>
            <div class="flex items-center gap-2 text-xs text-text-secondary">
              <PhTrendUp :size="14" class="text-success" />
              <span>{{ totalRequests }} requests in selected window</span>
            </div>
          </div>
        </div>
      </div>

      <div class="space-y-6">
        <div class="bg-bg-elevated border border-border rounded-lg p-5 shadow-soft">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-text-primary uppercase tracking-wide">Usage Timeline</h3>
            <span class="text-xs text-text-tertiary">{{ usageStore.timeline.length }} points</span>
          </div>
          <div class="space-y-2">
            <div
              v-for="point in usageStore.timeline"
              :key="point.date"
              class="flex items-center gap-3"
            >
              <span class="w-24 text-xs text-text-tertiary">{{ point.date }}</span>
              <div class="flex-1 h-2 rounded-full bg-primary-200 overflow-hidden">
                <div
                  class="h-full bg-brand"
                  :style="{ width: `${(point.totalRequestCount / maxRequests) * 100}%` }"
                />
              </div>
              <span class="text-xs text-text-secondary">{{ point.totalRequestCount }}</span>
            </div>
          </div>
        </div>

        <div class="bg-bg-elevated border border-border rounded-lg p-5 shadow-soft">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-text-primary uppercase tracking-wide">Model Mix</h3>
          </div>
          <div class="space-y-2 text-xs">
            <div v-for="[provider, cost] in modelMix" :key="provider" class="flex items-center justify-between text-text-secondary">
              <span>{{ provider }}</span>
              <span class="text-text-primary">${{ cost.toFixed(4) }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="space-y-6 xl:col-span-2 2xl:col-span-1">
        <div class="bg-bg-elevated border border-border rounded-lg p-5 shadow-soft">
          <h3 class="text-sm font-semibold text-text-primary uppercase tracking-wide mb-3 px-3">Error Stream</h3>
          <div class="space-y-2">
            <div
              v-for="(error, index) in usageStore.errors"
              :key="`${error.timestamp}-${index}`"
              class="bg-bg-tertiary border border-border rounded-md px-3 py-2 text-xs"
            >
              <div class="flex items-center justify-between text-text-tertiary">
                <span>{{ new Date(error.timestamp).toLocaleString() }}</span>
                <span class="text-error">{{ error.errorType }}</span>
              </div>
              <div class="text-text-primary mt-1">{{ error.message }}</div>
            </div>
            <div v-if="usageStore.errors.length === 0" class="text-xs text-text-tertiary px-3">No recent errors.</div>
          </div>
        </div>

        <div class="bg-primary-100 border border-border rounded-lg p-5">
          <h3 class="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2 uppercase tracking-wide">
            <PhWarningCircle :size="16" class="text-text-secondary" />
            Recommendations
          </h3>
          <div class="space-y-2 text-xs text-text-secondary">
            <div>Monitor high utilization windows before freeze.</div>
            <div>Review recurring provider errors in `usage/errors`.</div>
            <div>Use `tasks/stats` + `usage/timeline` during release gate.</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
