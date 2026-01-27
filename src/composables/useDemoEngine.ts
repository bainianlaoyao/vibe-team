import { ref, watch } from 'vue'
import type { DemoEvent } from '../types/demo'

export function useDemoEngine(script: DemoEvent[]) {
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const currentEventIndex = ref(0)
  const speed = ref(1) // Playback speed multiplier

  const play = () => {
    isPlaying.value = true
  }

  const pause = () => {
    isPlaying.value = false
  }

  const reset = () => {
    isPlaying.value = false
    currentTime.value = 0
    currentEventIndex.value = 0
  }

  const seek = (timeMs: number) => {
    currentTime.value = timeMs
    // Find the appropriate event index
    const index = script.findIndex(e => e.time_ms > timeMs) - 1
    currentEventIndex.value = Math.max(0, index)
  }

  // Timer for playback
  let startTime: number | null = null
  let animationFrame: number | null = null

  const tick = (timestamp: number) => {
    if (!isPlaying.value) return

    if (startTime === null) {
      startTime = timestamp - currentTime.value
    }

    const elapsed = (timestamp - startTime) * speed.value
    currentTime.value = elapsed

    // Update event index
    while (currentEventIndex.value < script.length - 1 &&
           script[currentEventIndex.value + 1].time_ms <= elapsed) {
      currentEventIndex.value++
    }

    // Check if demo is complete
    if (currentEventIndex.value >= script.length - 1) {
      isPlaying.value = false
      return
    }

    animationFrame = requestAnimationFrame(tick)
  }

  watch(isPlaying, (playing) => {
    if (playing) {
      startTime = null
      animationFrame = requestAnimationFrame(tick)
    } else if (animationFrame) {
      cancelAnimationFrame(animationFrame)
      animationFrame = null
    }
  })

  const getCurrentEvent = () => {
    return script[currentEventIndex.value]
  }

  const getCompletedEvents = () => {
    return script.slice(0, currentEventIndex.value + 1)
  }

  const getProgress = () => {
    if (script.length === 0) return 0
    const totalTime = script[script.length - 1].time_ms
    return (currentTime.value / totalTime) * 100
  }

  return {
    isPlaying,
    currentTime,
    currentEventIndex,
    speed,
    play,
    pause,
    reset,
    seek,
    getCurrentEvent,
    getCompletedEvents,
    getProgress
  }
}
