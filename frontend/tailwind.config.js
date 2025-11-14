/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
      '../templates/**/*.html',
      '../apps/**/templates/**/*.html',
      '../apps/**/*.py',
  ],
  safelist: [
    'bg-yellow-100', 'bg-yellow-300', 'bg-yellow-400', 'bg-yellow-600',
    'text-yellow-500', 'text-yellow-600', 'text-yellow-400',
    'bg-orange-100', 'bg-orange-400', 'bg-orange-500', 'bg-orange-600',
    'text-orange-500', 'text-orange-600',
    'bg-green-100', 'bg-green-300', 'bg-green-500',
    'text-green-500', 'text-green-600',
    'bg-red-400',
    // Dashboard dynamic badges (added to avoid purge)
    'bg-accent-green', 'bg-warm-orange-400', 'bg-terracotta-400', 'bg-terracotta-500',
    'border-accent-green', 'border-warm-orange-400', 'border-terracotta-400', 'border-terracotta-500',
    'text-accent-green', 'text-warm-orange-400', 'text-terracotta-400', 'text-terracotta-500',
    'bg-cream-200', 'bg-cream-50',
    'col-span-2', 'lg:col-span-2',
    // Alert styles (gradientes y colores pastel)
    'bg-gradient-to-b', 'from-yellow-300', 'to-yellow-400',
    'from-warm-orange-400', 'to-warm-orange-500',
    'from-terracotta-400', 'to-terracotta-500',
    'from-red-400',
    'bg-peach-200', 'bg-pink-200',
    'dark:bg-yellow-300/20', 'dark:bg-warm-orange-400/20', 
    'dark:bg-terracotta-400/20', 'dark:bg-red-400/20',
  ],
  theme: {
    extend: {
      colors: {
        // Colores principales del diseño
        'cream': {
          50: '#FBF7F0',
          100: '#F5EFE6',
          200: '#EDE4D6',
        },
        'peach': {
          100: '#F9E5D8',
          200: '#F0D4C3',
          300: '#E8C4B0',
        },
        'pink': {
          50: '#FFF0F5',
          100: '#FFE4EC',
          200: '#FFC9DC',
          300: '#FFB0CC',
        },
        'sage': {
          100: '#A8B5A8',
          200: '#8FA490',
        },
        'terracotta': {
          400: '#D4523F',
          500: '#C24232',
        },
        'warm-orange': {
          400: '#E89552',
          500: '#E89F5F',
        },
        
        // Paleta semántica para tema claro
        'background-primary': '#FBF7F0',
        'background-secondary': '#F5EFE6',
        'surface': '#FFFFFF',
        'border-color': '#E8DDD0',
        'text-primary': '#2C2C2C',
        'text-secondary': '#6B6B6B',
        'accent-peach': '#F9E5D8',
        'accent-green': '#8FA490',
        'alert-coral': '#E89552',
        
        // Paleta para tema oscuro
        'dark-background-primary': '#1A1A1A',
        'dark-background-secondary': '#242424',
        'dark-surface': '#2C2C2C',
        'dark-border-color': '#3F3F3F',
        'dark-text-primary': '#E8E8E8',
        'dark-text-secondary': '#A0A0A0',
        'dark-accent-peach': '#3D3028',
        'dark-accent-green': '#3D4A3E',
        'dark-alert-coral': '#E89552',
        'dark-pink': {
          100: '#3D2A34',
          200: '#4A3040',
        },
        
        orange: {
          100: '#FFE5C2',
          400: '#e89552',
          500: '#d4523f',
          600: '#c24232',
        },
        yellow: {
          100: '#FFF9C2',
          300: '#f0c76c',
          400: '#f7d774',
        },
        peach: {
          75: '#faeee1', 
        },
        green: {
          100: '#E6F9D5',
          300: '#a8c98f',
          500: '#4caf50',
        },
        red: {
          400: '#d4523f',
        },
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}