import type { Metadata } from "next";
import { Toaster } from "sonner";

import "./globals.css";

export const metadata: Metadata = {
  title: "JobHunter AI",
  description: "AI-powered job hunting assistant for Riyadh & Jeddah",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      {/* suppressHydrationWarning: browser extensions (e.g. ColorZilla's cz-shortcut-listen) add attributes to <body> */}
      <body className="min-h-screen font-sans" suppressHydrationWarning>
        {children}
        <Toaster richColors position="top-right" closeButton />
      </body>
    </html>
  );
}
