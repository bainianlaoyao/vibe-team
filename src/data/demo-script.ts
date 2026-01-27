import type { DemoEvent } from '../types/demo'

export const demoScript: DemoEvent[] = [
  {
    time_ms: 0,
    event: 'init_dashboard',
    project_name: 'SaaS Revenue Dashboard'
  },
  {
    time_ms: 1000,
    event: 'agent_start',
    agent_id: 'backend_01',
    role: 'Schema Architect',
    status: 'coding',
    log: 'Initializing Prisma Schema...'
  },
  {
    time_ms: 1200,
    event: 'agent_start',
    agent_id: 'frontend_01',
    role: 'UI Builder',
    status: 'blocked',
    reason: 'Waiting for Database Schema',
    log: 'Standby...'
  },
  {
    time_ms: 1500,
    event: 'agent_start',
    agent_id: 'design_01',
    role: 'Design System',
    status: 'coding',
    log: 'Setting up Tailwind config...'
  },
  {
    time_ms: 3500,
    event: 'file_created',
    path: '/prisma/schema.prisma',
    content_preview: 'model User { id String ... }',
    agent_id: 'backend_01'
  },
  {
    time_ms: 3800,
    event: 'agent_status_change',
    agent_id: 'backend_01',
    status: 'done',
    log: 'Schema complete ✓'
  },
  {
    time_ms: 4000,
    event: 'agent_status_change',
    agent_id: 'frontend_01',
    status: 'coding',
    log: 'Schema received. Generating Components...'
  },
  {
    time_ms: 5000,
    event: 'file_created',
    path: '/components/Button.tsx',
    content_preview: 'export function Button()',
    agent_id: 'design_01'
  },
  {
    time_ms: 6000,
    event: 'preview_update',
    view_state: 'skeleton_screen',
    description: 'Navigation bar appearing...'
  },
  {
    time_ms: 7500,
    event: 'file_created',
    path: '/pages/dashboard.tsx',
    content_preview: 'export default function Dashboard()',
    agent_id: 'frontend_01'
  },
  {
    time_ms: 8500,
    event: 'preview_update',
    view_state: 'partial',
    description: 'Dashboard layout loading...'
  },
  {
    time_ms: 10000,
    event: 'agent_status_change',
    agent_id: 'design_01',
    status: 'done',
    log: 'Design system ready ✓'
  },
  {
    time_ms: 12000,
    event: 'preview_update',
    view_state: 'full_ui_v1',
    description: 'Full UI rendered!'
  },
  {
    time_ms: 13000,
    event: 'agent_status_change',
    agent_id: 'frontend_01',
    status: 'done',
    log: 'All components ready ✓'
  },
  {
    time_ms: 14000,
    event: 'demo_complete',
    message: '🎉 Team mission accomplished!'
  }
]
