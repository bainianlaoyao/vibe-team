import { defineStore } from 'pinia';
import { ref } from 'vue';
import { ApiRequestError, api } from '../services/api';
import type { RoleProfile } from '../types';

export const useRolesStore = defineStore('roles', () => {
  const projectId = ref<number>(api.getProjectId());
  const roles = ref<RoleProfile[]>([]);
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  async function fetchRoles(): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      roles.value = await api.listRoles(projectId.value);
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to load roles.';
    } finally {
      loading.value = false;
    }
  }

  async function createRole(input: Omit<RoleProfile, 'id'>): Promise<void> {
    try {
      const created = await api.createRole(projectId.value, input);
      roles.value = [created, ...roles.value];
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to create role.';
    }
  }

  async function updateRole(role: RoleProfile): Promise<void> {
    try {
      const updated = await api.updateRole(projectId.value, role);
      roles.value = roles.value.map(item => (item.id === role.id ? updated : item));
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to update role.';
    }
  }

  async function deleteRole(roleId: string): Promise<void> {
    try {
      await api.deleteRole(projectId.value, roleId);
      roles.value = roles.value.filter(role => role.id !== roleId);
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to delete role.';
    }
  }

  return {
    projectId,
    roles,
    loading,
    error,
    fetchRoles,
    createRole,
    updateRole,
    deleteRole,
  };
});
