import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Consolas", "monospace"],
      },
      colors: {
        bg: "var(--bg, #0F1117)",
        "bg-elev": "var(--bg-elev, #0e1118)",
        surface: { DEFAULT: "var(--surface, #1A1D27)", 2: "var(--surface-2, #161b26)", 3: "var(--surface-3, #1b212e)" },
        border: { DEFAULT: "var(--border, #2A2D37)", hover: "var(--border-strong, #3A3D47)", strong: "var(--border-strong, #303a4b)" },
        terminal: "var(--term-bg, #0D1017)",
        "term-bg": "var(--term-bg, #07090d)",
        "term-green": "var(--term-green, #6ee7a0)",
        "term-dim": "var(--term-dim, #4a6a57)",
        "term-amber": "#ffcb6b",
        cyan: "#4FC3F7",
        accent: { DEFAULT: "var(--accent, #5bb8ff)", 2: "var(--accent-2, #8b7dff)" },
        amber: "#FFCA28",
        red: "#EF5350",
        green: "#66BB6A",
        orange: "#FF8A65",
        "pri-high": "var(--pri-high, #ef5350)",
        "pri-med": "var(--pri-med, #ffc93c)",
        "pri-low": "var(--pri-low, #4cc38a)",
        coin: "var(--coin, #ffc93c)",
        "text-primary": "var(--text, #e7edf4)",
        "text-secondary": "var(--text-muted, #8b97a8)",
        "text-tertiary": "var(--text-faint, #5c6675)",
      },
      maxWidth: { content: "1200px" },
      borderRadius: { card: "12px" },
      boxShadow: {
        card: "0 8px 28px -8px rgba(0,0,0,.6)",
        "card-hover": "0 24px 60px -16px rgba(0,0,0,.7)",
      },
      keyframes: {
        blink: { "50%": { opacity: "0" } },
      },
      animation: {
        blink: "blink 1.1s steps(1) infinite",
      },
    },
  },
  plugins: [],
};
export default config;
