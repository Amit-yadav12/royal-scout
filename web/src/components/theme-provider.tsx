"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { Moon, Sun } from "lucide-react";

type Theme = "light" | "dark";
type ThemeContextValue = { theme: Theme | null; toggle: () => void };
const ThemeContext = createContext<ThemeContextValue>({ theme: null, toggle: () => undefined });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    let saved: string | null = null;
    try { saved = window.localStorage.getItem("royal-scout-theme"); } catch { /* Private browsing can disable storage; system preference still works. */ }
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    setTheme(saved === "light" || saved === "dark" ? saved : media?.matches ? "dark" : "light");
  }, []);

  useEffect(() => {
    if (!theme) return;
    const root = document.documentElement;
    root.dataset.theme = theme;
    root.style.colorScheme = theme;
    try { window.localStorage.setItem("royal-scout-theme", theme); } catch { /* Theme still applies when browser storage is unavailable. */ }
  }, [theme]);

  const value = useMemo(() => ({
    theme,
    toggle: () => setTheme((current) => current === "dark" ? "light" : "dark"),
  }), [theme]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function ThemeToggle() {
  const { theme, toggle } = useContext(ThemeContext);
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button className="btn" type="button" onClick={toggle} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`}>
      {theme === "dark" ? <Sun className="h-3.5 w-3.5" aria-hidden="true" /> : <Moon className="h-3.5 w-3.5" aria-hidden="true" />}
      <span className="sr-only">{theme === "dark" ? "Light" : "Dark"} theme</span>
    </button>
  );
}
