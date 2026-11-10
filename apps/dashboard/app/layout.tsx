import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Shahid Workforce Dashboard",
  description: "Operator console for the Shahid Workforce agent platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <header className="app-header">
          <span className="app-brand">Shahid Workforce</span>
          <span className="app-subtitle">Agent Operations Console</span>
          <nav className="app-nav">
            <Link href="/">Tasks</Link>
            <Link href="/agents">Agents</Link>
          </nav>
        </header>
        <main className="app-main">{children}</main>
      </body>
    </html>
  );
}
