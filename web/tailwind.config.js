/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        // Light blueish theme — professional, calm, minimal
        // Primary is blue-500 (#3B82F6) and blue-50 (#EFF6FF) from default palette
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
