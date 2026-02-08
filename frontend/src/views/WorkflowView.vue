<script setup lang="ts">
import { ref } from 'vue';
import { mockTasks, mockAgents } from '../data/mockData';
import type { Task } from '../types';
import Avatar from '../components/Avatar.vue';
import {
  PhArrowsOutCardinal,
  PhMagnifyingGlassPlus,
  PhMagnifyingGlassMinus,
  PhFloppyDisk,
  PhTrash,
} from '@phosphor-icons/vue';

interface CanvasTask {
  task: Task;
  x: number;
  y: number;
}

const canvasTasks = ref<CanvasTask[]>(
  [mockTasks[0], mockTasks[1], mockTasks[2], mockTasks[3]]
    .filter((t): t is Task => t !== undefined)
    .map((task, index) => ({
      task,
      x: index % 2 === 0 ? 100 : 400,
      y: index < 2 ? 100 : 300,
    }))
);
const zoom = ref(1);
const canvasRef = ref<HTMLDivElement | null>(null);

const availableTasks = mockTasks.filter(task => !canvasTasks.value.find(ct => ct.task.id === task.id));
const getAgentById = (agentId: string | null) => agentId ? mockAgents.find(agent => agent.id === agentId) : undefined;

const handleZoomIn = () => { zoom.value = Math.min(zoom.value + 0.1, 2); };
const handleZoomOut = () => { zoom.value = Math.max(zoom.value - 0.1, 0.5); };

const handleDragStart = (e: DragEvent, task: Task) => {
  e.dataTransfer!.effectAllowed = 'copy';
  e.dataTransfer!.setData('taskId', task.id);
};

const handleCanvasDrop = (e: DragEvent) => {
  e.preventDefault();
  const taskId = e.dataTransfer!.getData('taskId');
  const task = mockTasks.find(t => t.id === taskId);
  if (task && canvasRef.value) {
    const rect = canvasRef.value.getBoundingClientRect();
    const x = (e.clientX - rect.left) / zoom.value;
    const y = (e.clientY - rect.top) / zoom.value;
    if (!canvasTasks.value.some(ct => ct.task.id === task.id)) {
      canvasTasks.value = [...canvasTasks.value, { task, x, y }];
    }
  }
};

const removeTaskFromCanvas = (taskId: string) => {
  canvasTasks.value = canvasTasks.value.filter(ct => ct.task.id !== taskId);
};
</script>

<template>
  <div class="flex-1 flex overflow-hidden">
    <!-- Sidebar -->
    <div class="w-64 bg-bg-tertiary border-r border-border p-4 overflow-y-auto">
      <div class="mb-6">
        <h3 class="text-xs font-semibold text-text-primary mb-3 uppercase tracking-wide">Available Tasks</h3>
        <div class="space-y-2">
          <div
            v-for="task in availableTasks"
            :key="task.id"
            draggable="true"
            class="bg-bg-elevated border border-border rounded p-3 cursor-move hover:shadow-soft transition-shadow"
            @dragstart="handleDragStart($event, task)"
          >
            <div class="flex items-center gap-2 mb-1">
              <span class="text-xs font-mono text-text-tertiary">#{{ task.id.split('-')[1] }}</span>
            </div>
            <div class="text-xs font-medium text-text-primary line-clamp-2">{{ task.title }}</div>
          </div>
        </div>
      </div>

      <div class="mb-6">
        <h3 class="text-xs font-semibold text-text-primary mb-3 uppercase tracking-wide">Agents</h3>
        <div class="space-y-2">
          <div
            v-for="agent in mockAgents"
            :key="agent.id"
            class="bg-bg-elevated border border-border rounded p-3"
          >
            <div class="flex items-center gap-2">
              <Avatar
                :src="agent.avatar"
                :alt="agent.name"
                :fallback="agent.name[0]"
                container-class="w-7 h-7 rounded-md"
                text-class="text-[12px]"
              />
              <span class="text-xs text-text-secondary">{{ agent.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Canvas -->
    <div class="flex-1 flex flex-col">
      <!-- Toolbar -->
      <div class="bg-bg-tertiary border-b border-border px-4 py-3 flex items-center justify-between">
        <div class="flex items-center gap-2">
          <button class="p-2 hover:bg-bg-elevated rounded transition-colors">
            <PhArrowsOutCardinal :size="18" />
          </button>
          <div class="w-px h-6 bg-gray-300 mx-2" />
          <button class="p-2 hover:bg-bg-elevated rounded transition-colors" @click="handleZoomOut">
            <PhMagnifyingGlassMinus :size="18" />
          </button>
          <span class="text-sm text-text-secondary px-2">{{ Math.round(zoom * 100) }}%</span>
          <button class="p-2 hover:bg-bg-elevated rounded transition-colors" @click="handleZoomIn">
            <PhMagnifyingGlassPlus :size="18" />
          </button>
        </div>
        <div class="flex items-center gap-2">
          <button class="flex items-center gap-2 px-3 py-2 text-xs bg-brand hover:bg-brand/90 text-white rounded transition-colors">
            <PhFloppyDisk :size="16" />
            <span>Save Workflow</span>
          </button>
          <button class="flex items-center gap-2 px-3 py-2 text-xs bg-error hover:bg-error/90 text-white rounded transition-colors">
            <PhTrash :size="16" />
            <span>Clear</span>
          </button>
        </div>
      </div>

      <!-- Canvas Area -->
      <div
        ref="canvasRef"
        class="flex-1 bg-bg-elevated overflow-hidden relative"
        style="background-image: radial-gradient(circle, #e3e3de 1px, transparent 1px); background-size: 20px 20px;"
        @drop="handleCanvasDrop"
        @dragover.prevent
      >
        <div
          :style="{ transform: `scale(${zoom})`, transformOrigin: '0 0' }"
          class="relative w-full h-full"
        >
          <!-- Task Cards -->
          <div
            v-for="{ task, x, y } in canvasTasks"
            :key="task.id"
            class="absolute bg-bg-elevated border border-border rounded-lg p-4 shadow-soft cursor-move hover:shadow-medium transition-shadow"
            :style="{ left: `${x}px`, top: `${y}px`, width: '200px' }"
          >
            <button
              class="absolute top-2 right-2 text-text-tertiary hover:text-error"
              @click="removeTaskFromCanvas(task.id)"
            >
              ✕
            </button>
            <div class="flex items-center gap-2 mb-2">
              <span class="text-xs font-mono text-text-tertiary">#{{ task.id.split('-')[1] }}</span>
            </div>
            <h4 class="text-sm font-semibold text-text-primary mb-2 line-clamp-2">{{ task.title }}</h4>
            <div v-if="getAgentById(task.assignedTo)" class="flex items-center gap-2 mt-3">
              <Avatar
                :src="getAgentById(task.assignedTo)?.avatar"
                :alt="getAgentById(task.assignedTo)?.name"
                :fallback="getAgentById(task.assignedTo)?.name?.[0] || 'A'"
                container-class="w-6 h-6 rounded-md"
                text-class="text-[12px]"
              />
              <span class="text-xs text-text-secondary">{{ getAgentById(task.assignedTo)?.name }}</span>
            </div>
            <div class="mt-2 text-xs text-text-tertiary">
              Status: <span class="capitalize">{{ task.status.replace('_', ' ') }}</span>
            </div>
          </div>
        </div>

        <div v-if="canvasTasks.length === 0" class="absolute inset-0 flex items-center justify-center">
          <div class="text-center text-text-tertiary">
            <p class="text-lg mb-2">Drag tasks from the sidebar to start</p>
            <p class="text-sm">Create visual workflows by connecting tasks</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
