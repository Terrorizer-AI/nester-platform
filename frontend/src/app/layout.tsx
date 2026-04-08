import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import ThemeToggle from "@/components/ThemeToggle";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Nester Agent Platform",
  description: "Build Once. Configure Many. Deploy Any Flow.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body suppressHydrationWarning className="min-h-full flex flex-col bg-background text-foreground font-sans">
        <nav className="fixed top-0 w-full z-50 glass border-b border-outline/20 h-14 flex items-center px-10 justify-between">
          <div className="flex items-center gap-10">
            <a href="/" className="flex items-center">
              <img src="/nester-logo.svg" alt="Nester" className="h-6 theme-logo" />
            </a>
            <div className="hidden md:flex gap-6">
              {[
                { href: "/", label: "Dashboard" },
                { href: "/flow/sales_outreach", label: "Outreach" },
                { href: "/sow", label: "SOW Generator" },
                { href: "/history", label: "History" },
                { href: "/chat", label: "Chat" },
                { href: "/integrations", label: "Integrations" },
                { href: "/knowledge", label: "Knowledge" },
                { href: "/settings", label: "API Keys" },
              ].map((link) => (
                <a
                  key={link.href}
                  href={link.href}
                  className="text-[0.6875rem] uppercase tracking-widest font-bold text-foreground/50 hover:text-accent-dim transition-colors"
                >
                  {link.label}
                </a>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <div className="w-7 h-7 rounded-full bg-accent/20 border border-accent/30 flex items-center justify-center overflow-hidden">
              <img src="/nester-logo.svg" alt="N" className="h-4 theme-logo" />
            </div>
          </div>
        </nav>
        <main className="flex-1 pt-14">{children}</main>
      </body>
    </html>
  );
}
