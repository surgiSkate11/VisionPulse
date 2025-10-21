/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
      '../templates/**/*.html',
      '../apps/**/templates/**/*.html',
      '../apps/**/*.py',
  ],
  theme: {
    extend: {
      colors: {
        'background-primary': '#F5EFE7',
        'surface': '#FFFBF5',
        'text-primary': '#4A4238',
        'text-secondary': '#8C7E6A',
        'border-color': 'rgba(140, 126, 106, 0.2)',
        'accent-green': '#A8B89F',
        'accent-peach': '#FFD3BA',
        'alert-amber': '#F4A261',
        'alert-coral': '#D4735E',
        // Colores para el modo oscuro
        dark: {
          'background-primary': '#1E1E24',
          'surface': '#2A2A32',
          'text-primary': '#E6E1D9',
          'text-secondary': '#B8B2A6',
          'border-color': 'rgba(184, 178, 166, 0.2)',
          'accent-green': '#8FA087',
          'accent-peach': '#E6B8A2',
        },
      },
      fontFamily: {
        sans: ['Inter', 'Nunito', 'sans-serif'],
      },
    },
  },
  plugins: [],
}