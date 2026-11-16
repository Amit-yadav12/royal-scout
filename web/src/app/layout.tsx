import type { Metadata } from "next";
import "./globals.css";
import { Shell } from "@/components/shell";

export const metadata: Metadata = {
  title: "Royal Scout Intelligence Hub — Every Player. Every Metric. Every Insight.",
  description:
    "IPL / domestic cricket player intelligence, performance analytics and scouting dashboard for evidence-based Top 30 batters and bowlers.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
