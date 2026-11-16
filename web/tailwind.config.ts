import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 950: "#080E1D", 900: "#101B34", 800: "#182746", 700: "#23416F", 600: "#315384" },
        royal: { pink: "#D72D79", pinkDark: "#B51F62", gold: "#C9A45C", blue: "#254B84" },
        surface: {
          DEFAULT: "rgb(var(--rs-surface) / <alpha-value>)",
          muted: "rgb(var(--rs-surface-muted) / <alpha-value>)",
          line: "rgb(var(--rs-surface-line) / <alpha-value>)",
          deep: "rgb(var(--rs-surface-deep) / <alpha-value>)",
        },
        ink: {
          DEFAULT: "rgb(var(--rs-ink) / <alpha-value>)",
          soft: "rgb(var(--rs-ink-soft) / <alpha-value>)",
          faint: "rgb(var(--rs-ink-faint) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: { "2xs": ["0.6875rem", { lineHeight: "1rem" }] },
      boxShadow: {
        card: "0 1px 2px rgba(11,27,51,0.04), 0 1px 3px rgba(11,27,51,0.06)",
        pop: "0 8px 30px rgba(11,27,51,0.12)",
      },
      keyframes: {
        "fade-up": { "0%": { opacity: "0", transform: "translateY(4px)" }, "100%": { opacity: "1", transform: "none" } },
      },
      animation: { "fade-up": "fade-up 220ms ease-out both" },
    },
  },
  plugins: [],
};
export default config;
