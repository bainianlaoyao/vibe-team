import { createRouter, createWebHistory } from 'vue-router';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../views/DashboardView.vue'),
    },
    {
      path: '/inbox',
      name: 'inbox',
      component: () => import('../views/InboxView.vue'),
    },
    {
      path: '/chat',
      name: 'chat',
      component: () => import('../views/ChatView.vue'),
    },
    {
      path: '/agents',
      redirect: '/agents/table',
    },
    {
      path: '/agents/table',
      name: 'agents-table',
      component: () => import('../views/TableView.vue'),
    },
    {
      path: '/agents/kanban',
      name: 'agents-kanban',
      component: () => import('../views/KanbanView.vue'),
    },
    {
      path: '/agents/customize',
      name: 'agents-customize',
      component: () => import('../views/CustomizeView.vue'),
    },
    {
      path: '/workflow',
      name: 'workflow',
      component: () => import('../views/WorkflowView.vue'),
    },
    {
      path: '/files',
      name: 'files',
      component: () => import('../views/FilesView.vue'),
    },
    {
      path: '/files/view/:id',
      name: 'file-viewer',
      component: () => import('../views/FileViewer.vue'),
    },
    {
      path: '/roles',
      name: 'roles',
      component: () => import('../views/RolesView.vue'),
    },
    {
      path: '/api',
      name: 'api',
      component: () => import('../views/ApiView.vue'),
    },
  ],
});

export default router;
