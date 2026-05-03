/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy:    { DEFAULT: '#0d1117', 800: '#0d1117', 700: '#161b22', 600: '#21262d', 500: '#30363d' },
        orange:  { DEFAULT: '#e8780a', light: '#f89422', dark: '#c0600a' },
        slate:   { panel: '#1c2128', border: '#30363d' },
        success: '#3fb950',
        danger:  '#f85149',
        warning: '#d29922',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Courier New', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
