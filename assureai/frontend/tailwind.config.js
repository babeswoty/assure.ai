/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Deloitte brand palette (green accent, black/grey neutrals) -
        // applied as the accent color only; layout stays plain per the
        // "test harness, not branding exercise" instruction.
        brand: {
          50: "#f0f7e3",
          100: "#dcedbd",
          200: "#c0df8c",
          300: "#a3d15c",
          400: "#93c53e",
          500: "#86bc25", // Deloitte green
          600: "#6d9a1e",
          700: "#557818",
          800: "#3d5711",
          900: "#26360b",
          950: "#141d05",
        },
        ink: {
          50: "#f5f5f5",
          100: "#e6e6e6",
          200: "#c2c2c2",
          300: "#9e9e9e",
          400: "#6b6b6b",
          500: "#404040",
          600: "#2c2c2c",
          700: "#1f1f1f",
          800: "#141414",
          900: "#0a0a0a",
          950: "#000000", // Deloitte black
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px 0 rgba(0,0,0,0.06), 0 1px 3px 0 rgba(0,0,0,0.08)",
      },
    },
  },
  plugins: [],
};
