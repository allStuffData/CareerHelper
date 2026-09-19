import type { Metadata } from "next";
import Link from "next/link";

import "./globals.css";

export const metadata: Metadata = {
  title: "CareerHelper — Tailored resumes from a job description",
  description:
    "Paste a job description and generate an ATS-optimized, one-page PDF resume.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="site-header__inner">
            <Link href="/" className="brand">
              Career<span>Helper</span>
            </Link>
            <nav className="nav" aria-label="Primary">
              <Link href="/">Generate</Link>
              <Link href="/history">History</Link>
              <Link href="/templates">Templates</Link>
            </nav>
          </div>
        </header>
        <main className="container">{children}</main>
      </body>
    </html>
  );
}
