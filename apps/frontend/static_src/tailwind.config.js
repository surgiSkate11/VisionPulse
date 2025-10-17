module.exports = {
  content: [
    '../../../templates/**/*.html',
    '../../../**/templates/**/*.html',
    '../../../apps/**/*.py',
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
      },
      fontFamily: {
        sans: ['Inter', 'Nunito', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
