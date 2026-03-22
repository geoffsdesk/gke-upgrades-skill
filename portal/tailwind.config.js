/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        gke: {
          blue: '#1a73e8',
          'dark-blue': '#174ea6',
          green: '#1e8e3e',
          red: '#d93025',
          orange: '#e37400',
          gray: '#5f6368',
          'light-gray': '#f1f3f4',
          dark: '#202124',
        },
      },
    },
  },
  plugins: [],
}
