import { defineStore } from 'pinia';
import { computed, ref } from 'vue';
import { ApiRequestError, api } from '../services/api';
import type { FileNode, PermissionLevel } from '../types';

function findNodeById(root: FileNode | null, id: string): FileNode | null {
  if (!root) return null;
  if (root.id === id) return root;
  for (const child of root.children) {
    const found = findNodeById(child, id);
    if (found) return found;
  }
  return null;
}

function findPathToId(root: FileNode | null, id: string, path: FileNode[] = []): FileNode[] | null {
  if (!root) return null;
  const currentPath = [...path, root];
  if (root.id === id) return currentPath;
  for (const child of root.children) {
    const found = findPathToId(child, id, currentPath);
    if (found) return found;
  }
  return null;
}

export const useFileSystemStore = defineStore('fileSystem', () => {
  const projectId = ref<number>(api.getProjectId());
  const root = ref<FileNode | null>(null);
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  const rootChildren = computed(() => root.value?.children || []);

  async function fetchTree(path = '.', maxDepth = 4): Promise<void> {
    loading.value = true;
    error.value = null;
    try {
      root.value = await api.getFilesTree(projectId.value, path, maxDepth);
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError ? `${apiError.code}: ${apiError.message}` : 'Failed to load files.';
    } finally {
      loading.value = false;
    }
  }

  async function setPermission(id: string, level: PermissionLevel | 'inherit'): Promise<void> {
    try {
      await api.updateFilePermission(projectId.value, id, level);
      await fetchTree('.', 5);
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to update file permission.';
    }
  }

  function getExplicitPermission(id: string): PermissionLevel | null {
    const node = findNodeById(root.value, id);
    return node?.permission || null;
  }

  function getEffectivePermission(id: string): PermissionLevel {
    const node = findNodeById(root.value, id);
    return node?.permission || 'read';
  }

  function getEffectivePermissionForPath(path: FileNode[]): PermissionLevel {
    const last = path[path.length - 1];
    return last?.permission || 'read';
  }

  async function getFileContent(id: string): Promise<string | null> {
    try {
      const payload = await api.getFileContent(projectId.value, id);
      return payload.content;
    } catch (cause) {
      const apiError = cause instanceof ApiRequestError ? cause : null;
      error.value = apiError
        ? `${apiError.code}: ${apiError.message}`
        : 'Failed to load file content.';
      return null;
    }
  }

  return {
    projectId,
    root,
    rootChildren,
    loading,
    error,
    fetchTree,
    setPermission,
    getExplicitPermission,
    getEffectivePermission,
    getEffectivePermissionForPath,
    getFileContent,
    findNodeById: (id: string) => findNodeById(root.value, id),
    findPathToId: (id: string) => findPathToId(root.value, id),
  };
});
