import type { Metadata } from "next";
import { Inter } from "next/font/google";

import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "SYNAPSE — Workflow Compiler",
  description: "Intelligent AI workflow compiler, execution runtime and observability engine.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // Dark-only surface: the palette lives on :root and `dark` is kept so the
    // shadcn primitives' `dark:` variants resolve.
    <html lang="en" className="dark">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
