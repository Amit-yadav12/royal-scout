import type { Metadata, Viewport } from "next";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";

export const metadata: Metadata = {
  title: "Royal Scout Intelligence OS — Every Player. Every Metric. Every Insight.",
  description: "A provenance-first cricket scouting and performance intelligence platform.",
  icons: { icon: "/royal-scout-favicon.png" },
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#F4F6FA" }, { media: "(prefers-color-scheme: dark)", color: "#080E1D" }],
  colorScheme: "light dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body><ThemeProvider>{children}</ThemeProvider></body>
    </html>
  );
}
