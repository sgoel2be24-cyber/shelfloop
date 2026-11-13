/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ivory: '#F5F7F3',
        brand: '#174C3C',
        accent: '#D86736',
        ink: '#21352D',
      },
      fontFamily: {
        sans: [
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          '"Baloo 2"',
          'sans-serif',
        ],
        display: ['system-ui', '"Baloo 2"', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
