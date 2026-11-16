import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: { 950: "#050D1B", 900: "#0B1B33", 800: "#102A54", 700: "#173C74", 600: "#1F5296" },
        royal: { pink: "#E8117F", pinkDark: "#B70D64", gold: "#C9A227", blue: "#1B4B8F" },
        surface: { DEFAULT: "#FFFFFF", muted: "#F7F8FA", line: "#E4E8EF", deep: "#EEF1F6" },
        ink: { DEFAULT: "#0B1B33", soft: "#4A5768", faint: "#7A8699" },
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
