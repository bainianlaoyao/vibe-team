/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Design System Colors
        'deep-space': '#0F1117',
        'glass-panel': '#1E232F',
        'electric-indigo': '#6366F1',
        'neon-green': '#10B981',
        'cyber-yellow': '#F59E0B',
        'signal-red': '#EF4444',
        'holographic-blue': '#3B82F6',
      },
      fontFamily: {
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      animation: {
        'pop-in': 'popIn 0.3s cubic-bezier(0.68, -0.55, 0.265, 1.55)',
        'pulse-glow': 'pulseGlow 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'spin-slow': 'spin 3s linear infinite',
      },
      keyframes: {
        popIn: {
          '0%': { transform: 'scale(0.5)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        pulseGlow: {
          '0%, 100%': { opacity: '1', boxShadow: '0 0 20px rgba(99, 102, 241, 0.5)' },
          '50%': { opacity: '0.7', boxShadow: '0 0 10px rgba(99, 102, 241, 0.3)' },
        },
      },
    },
  },
  plugins: [],
}
