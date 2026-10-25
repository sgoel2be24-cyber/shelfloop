/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ivory: '#FAF5EC',
        brand: '#2E3192',
        accent: '#E8702A',
        ink: '#1F2430',
      },
      fontFamily: {
        sans: [
          '"Baloo 2"',
          'Noto Sans Devanagari',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        display: ['"Baloo 2"', 'Noto Sans Devanagari', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
