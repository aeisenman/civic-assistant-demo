/**
 * Root layout: system font stack, slate-50 page, and the chrome switch.
 * Wraps every route. Depends on components/SiteChrome and app/globals.css.
 */

import type { Metadata } from "next";
import "./globals.css";
import SiteChrome from "@/components/SiteChrome";

export const metadata: Metadata = {
  title: "City of San Diego — Virtual Assistant (demo)",
  description: "Resident-facing assistant demo: chat, staff queue, and model traces.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="flex h-full flex-col bg-page text-ink">
        {/* SiteChrome renders the resident nav and footer, or steps aside under
            /staff so app/staff/layout.tsx can render the console's own. */}
        <SiteChrome>{children}</SiteChrome>
      </body>
    </html>
  );
}
