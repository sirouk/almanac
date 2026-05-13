import type { Metadata, Viewport } from "next";
import { Inter, Space_Grotesk } from "next/font/google";
import { PwaRegister } from "@/components/pwa-register";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-inter",
  display: "swap",
});

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  variable: "--font-space-grotesk",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_ARCLINK_SITE_URL || "https://arclink.online"),
  title: "ArcLink - Raven Runs Your Operations",
  description: "Deploy autonomous ArcLink agents with Raven for research, data movement, reporting, follow-up, and operational workflows.",
  applicationName: "ArcLink",
  manifest: "/manifest.webmanifest",
  openGraph: {
    title: "ArcLink - Raven Runs Your Operations",
    description: "Deploy autonomous ArcLink agents that connect to your tools and handle recurring operations.",
    images: ["/marketing/Arclink-share.png"],
  },
  appleWebApp: {
    capable: true,
    title: "ArcLink",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: "/marketing/Favicon.png",
    apple: "/marketing/Favicon.png",
  },
};

export const viewport: Viewport = {
  themeColor: "#080808",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${spaceGrotesk.variable}`}>
      <body className="min-h-screen bg-jet text-soft-white antialiased">
        <PwaRegister />
        {children}
      </body>
    </html>
  );
}
