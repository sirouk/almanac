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
  title: "ArcLink - Agents Onboard ArcLink",
  description: "Agents onboard ArcLink with memory, files, code workspace, and model access.",
  applicationName: "ArcLink",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    title: "ArcLink",
    statusBarStyle: "black-translucent",
  },
  icons: {
    icon: "/brand/raven/raven_pfp.webp",
    apple: "/brand/raven/raven_pfp.webp",
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
