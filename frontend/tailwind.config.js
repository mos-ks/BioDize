/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      colors: {
        // Brand: Rentschler Biopharma deep blue (#0045A5 = 600) — primary everywhere.
        brand: {
          50: "#eef4fc",
          100: "#d7e6f8",
          200: "#aecbf1",
          300: "#7ba8e6",
          400: "#4480d8",
          500: "#1a5ec4",
          600: "#0045A5",
          700: "#003c8c",
          800: "#06316f",
          900: "#0a2b5b",
          950: "#061a38",
        },
        // Accent: Rentschler bright yellow — key CTAs / highlights.
        accent: {
          50: "#fffbe6",
          100: "#fff4b8",
          200: "#ffec85",
          300: "#ffe24d",
          400: "#ffd91f",
          500: "#FFD700",
          600: "#e6c000",
          700: "#b89800",
          800: "#8a7100",
          900: "#5c4b00",
          DEFAULT: "#FFD700",
        },
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(15 23 42 / 0.04), 0 1px 3px 0 rgb(15 23 42 / 0.06)",
        panel: "0 4px 24px -8px rgb(15 23 42 / 0.12)",
      },
      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "slide-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "slide-up": "slide-up 0.22s ease-out",
        shimmer: "shimmer 1.4s infinite",
      },
    },
  },
  plugins: [],
};
