import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ApiRequestError, api } from '../services/api';
import type { UsageBudget, UsageError, UsageTimelinePoint } from '../types';

export const useUsageStore = defineStore('usage', () => {
  const projectId = ref<number>(api.getProjectId());
  const budget = ref<UsageBudget | null>(null);
  const timeline = ref<UsageTimelinePoint[]>([]);
  const errors = ref<UsageError[]>([]);
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  async function fetchUsage(days = 7): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      const [budgetData, timelineData, errorData] = await Promise.all([
        api.getUsageBudget(),
        api.getUsageTimeline(days),
        api.getUsageErrors(projectId.value),
      ]);
      budget.value = budgetData;
      timeline.value = timelineData;
      errors.value = errorData;
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to load usage metrics.';
    } finally {
      loading.value = false;
    }
  }

  return {
    projectId,
    budget,
    timeline,
    errors,
    loading,
    error,
    fetchUsage,
  };
});
