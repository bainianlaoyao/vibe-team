/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    borderRadius: {
      none: '0',
      sm: '0.125rem',
      DEFAULT: '0.25rem',
      md: '0.375rem',
      lg: '0.5rem',
      xl: '0.625rem',
      '2xl': '0.75rem',
      full: '9999px',
    },
    extend: {
      colors: {
        // Notion-like neutral palette
        primary: {
          50: '#f7f7f5',
          100: '#f1f1ef',
          200: '#e6e6e3',
          300: '#d2d2cd',
          400: '#b5b3ad',
          500: '#9a9892',
          600: '#6f6c66',
          700: '#4c4a46',
          800: '#2f2e2a',
          900: '#1f1e1b',
        },
        accent: {
          50: '#f3f7ff',
          100: '#e6efff',
          200: '#c7dcff',
          300: '#9fbff7',
          400: '#6f9ded',
          500: '#4a7fe0',
          600: '#3567c8',
          700: '#2a55a5',
          800: '#233f7a',
          900: '#1b2f57',
        },
        // Text colors with proper contrast
        'text-primary': 'var(--text)',
        'text-secondary': 'var(--text-secondary)',
        'text-tertiary': 'var(--text-tertiary)',
        'text-muted': '#b7bbc0',
        // Background colors
        'bg-primary': 'var(--panel)',
        'bg-secondary': 'var(--bg)',
        'bg-tertiary': 'var(--panel-muted)',
        'bg-elevated': 'var(--panel)',
        // Borders and state colors
        'border': 'var(--border)',
        // Legacy support (keeping for compatibility)
        'text-high': 'var(--text)',
        'text-normal': 'var(--text-secondary)',
        'text-low': 'var(--text-tertiary)',
        'bg-panel': 'var(--panel)',
        'brand': 'var(--accent)',
        'error': 'var(--error)',
        'success': 'var(--success)',
      },
      fontFamily: {
        sans: ['IBM Plex Sans', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['IBM Plex Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      fontSize: {
        'xs': ['0.75rem', { lineHeight: '1.05rem' }],     // 12px
        'sm': ['0.8125rem', { lineHeight: '1.2rem' }],    // 13px
        'base': ['0.84375rem', { lineHeight: '1.3rem' }], // 13.5px
        'lg': ['0.9375rem', { lineHeight: '1.4rem' }],    // 15px
        'xl': ['1.0625rem', { lineHeight: '1.55rem' }],   // 17px
        '2xl': ['1.25rem', { lineHeight: '1.7rem' }],     // 20px
        '3xl': ['1.5rem', { lineHeight: '2rem' }],        // 24px
        '4xl': ['1.875rem', { lineHeight: '2.4rem' }],    // 30px
      },
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
      },
      boxShadow: {
        'soft': '0 1px 2px rgba(44, 35, 28, 0.06)',
        'medium': '0 4px 10px rgba(44, 35, 28, 0.08)',
        'strong': '0 10px 24px rgba(44, 35, 28, 0.12)',
      },
      transitionDuration: {
        '250': '250ms',
      },
    },
  },
  plugins: [],
}
