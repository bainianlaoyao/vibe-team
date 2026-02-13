<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'

const props = defineProps<{
  show: boolean
  targetElement: string
  position: { x: number; y: number }
}>()

const emit = defineEmits<{
  close: []
  submit: [instruction: string]
}>()

const instruction = ref('')

const handleSubmit = () => {
  if (instruction.value.trim()) {
    emit('submit', instruction.value)
    instruction.value = ''
  }
}

// Focus input when shown
const focusInput = async () => {
  await nextTick()
  const input = document.querySelector('#directive-input') as HTMLInputElement
  input?.focus()
}

watch(
  () => props.show,
  (visible) => {
    if (!visible) {
      return
    }
    void focusInput()
  }
)
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div
        v-if="show"
        class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50"
        @click.self="emit('close')"
      >
        <!-- Spotlight Effect -->
        <div class="absolute inset-0 flex items-center justify-center">
          <!-- Connection Line -->
          <div
            class="absolute border-2 border-dashed border-electric-indigo/50"
            :style="{
              left: `${position.x}px`,
              top: `${position.y}px`,
              width: '2px',
              height: '100px',
              transform: 'rotate(-45deg)',
              transformOrigin: 'top center'
            }"
          ></div>

          <!-- Directive Card -->
          <div
            class="glass-strong rounded-2xl p-6 w-96 shadow-2xl shadow-electric-indigo/20
                   border border-electric-indigo/30 animate-pop-in"
            :style="{
              left: `${position.x + 100}px`,
              top: `${position.y - 50}px`,
              position: 'absolute'
            }"
          >
            <div class="flex items-center gap-3 mb-4">
              <div class="w-10 h-10 bg-gradient-to-br from-electric-indigo to-holographic-blue rounded-lg flex items-center justify-center">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <div>
                <h3 class="font-semibold">Directiva</h3>
                <p class="text-xs text-white/60">修改 {{ targetElement }}</p>
              </div>
            </div>

            <textarea
              id="directive-input"
              v-model="instruction"
              placeholder="输入你的指令... 例如：把这个按钮改成 Indigo 色，圆角大一点"
              class="w-full h-32 px-4 py-3 bg-white/5 border border-white/10 rounded-xl
                     focus:outline-none focus:border-electric-indigo/50 focus:bg-white/10
                     transition-all placeholder:text-white/30 resize-none text-sm"
              @keydown.ctrl.enter="handleSubmit"
            ></textarea>

            <div class="flex items-center justify-between mt-4">
              <span class="text-xs text-white/40">Ctrl + Enter to send</span>
              <div class="flex gap-2">
                <button
                  @click="emit('close')"
                  class="px-4 py-2 text-sm text-white/60 hover:text-white transition-colors"
                >
                  取消
                </button>
                <button
                  @click="handleSubmit"
                  class="px-4 py-2 bg-gradient-to-r from-electric-indigo to-holographic-blue
                         rounded-lg text-sm font-medium hover:shadow-lg hover:shadow-electric-indigo/30
                         transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                  :disabled="!instruction.trim()"
                >
                  发送指令
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
