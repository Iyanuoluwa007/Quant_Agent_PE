/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    './components/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          0: '#060a12',
          1: '#0b1120',
          2: '#111827',
          3: '#1a2236',
          4: '#243049',
        },
        accent: {
          blue: '#3b82f6',
          green: '#10b981',
          red: '#ef4444',
          amber: '#f59e0b',
          cyan: '#06b6d4',
        },
        text: {
          primary: '#e2e8f0',
          secondary: '#94a3b8',
          muted: '#64748b',
        },
        border: {
          DEFAULT: '#1e293b',
          bright: '#334155',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
        sans: ['Geist', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
