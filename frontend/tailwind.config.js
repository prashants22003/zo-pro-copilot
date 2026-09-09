/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14120F",
        "ink-1": "#1C1915",
        "ink-2": "#241F19",
        "text-hi": "#F5F0E6",
        "text-mid": "#B9AF9D",
        "text-low": "#756D5E",
        gold: "#E3A542",
        teal: "#2E6E62",
        ember: "#C1502E",
      },
      fontFamily: {
        voice: ['"Fraunces"', "serif"],
        ui: ['"Inter"', "sans-serif"],
        mono: ['"IBM Plex Mono"', "monospace"],
      },
      maxWidth: {
        river: "760px",
      },
    },
  },
  plugins: [],
};
