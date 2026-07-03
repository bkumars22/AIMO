/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // AIMO brand — dark observatory palette
        aimo: {
          bg:       '#030712', // gray-950
          surface:  '#111827', // gray-900
          border:   '#1f2937', // gray-800
          accent:   '#6366f1', // indigo-500
          critical: '#ef4444', // red-500
          warn:     '#f59e0b', // amber-500
          ok:       '#22c55e', // green-500
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}
