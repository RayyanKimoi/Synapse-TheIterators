import type { Metadata } from "next";
import { Inter, Montserrat, Playfair_Display } from "next/font/google";

import "./globals.css";

// Named distinctly from the semantic --font-* tokens so globals.css stays the
// single place that decides which face plays which role.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const montserrat = Montserrat({
  subsets: ["latin"],
  weight: ["500", "600", "700", "800"],
  variable: "--font-montserrat",
  display: "swap",
});
const playfair = Playfair_Display({
  subsets: ["latin"],
  style: ["normal", "italic"],
  variable: "--font-playfair",
  display: "swap",
});

export const metadata: Metadata = {
  title: "SYNAPSE — Deterministic Orchestration for AI Workflows",
  description:
    "SYNAPSE compiles agent workflows into dependency-aware parallel execution trees: deterministic orchestration, parallel execution and measurable cost optimization.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // Dark-only surface: the palette lives on :root and `dark` is kept so the
    // shadcn primitives' `dark:` variants resolve.
    <html
      lang="en"
      className={`dark ${inter.variable} ${montserrat.variable} ${playfair.variable}`}
    >
      <body className="font-sans">{children}</body>
    </html>
  );
}
