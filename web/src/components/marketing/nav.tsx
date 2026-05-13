"use client";

import Image from "next/image";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";

const links = [
  { label: "PRODUCT", href: "#solution" },
  { label: "HOW IT WORKS", href: "#how-it-works" },
  { label: "PRICING", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
];

export default function MarketingNav() {
  const [scrolled, setScrolled] = useState(false);
  const pathname = usePathname();
  const isHome = pathname === "/";

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const navHref = (href: string) => (isHome ? href : `/${href}`);

  return (
    <nav
      className={`fixed left-0 right-0 top-0 z-50 transition-all duration-300 ${
        scrolled ? "border-b border-white/5 bg-[#080808]/95 backdrop-blur-md" : "bg-transparent"
      }`}
    >
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 lg:px-8">
        <Link href="/" className="flex items-center" aria-label="ArcLink home">
          <Image
            src="/marketing/Arclink_v3--orange_symbol_white_text.svg"
            alt="ArcLink"
            width={154}
            height={32}
            className="h-8 w-auto"
            priority
          />
        </Link>
        <div className="hidden items-center gap-8 md:flex">
          {links.map((item) => (
            <Link
              key={item.label}
              href={navHref(item.href)}
              className="font-mono text-xs tracking-widest text-[#E7E6E6]/50 transition-colors hover:text-[#E7E6E6]"
            >
              {item.label}
            </Link>
          ))}
          <Link
            href="/login"
            className="font-mono text-xs tracking-widest text-[#E7E6E6]/50 transition-colors hover:text-[#E7E6E6]"
          >
            LOGIN
          </Link>
        </div>
        <Link
          href="/onboarding"
          className="flex items-center gap-2 rounded bg-[#FB5005] px-4 py-2.5 font-mono text-[10px] font-semibold tracking-widest text-white transition-colors hover:bg-[#e04504] sm:text-xs md:px-5"
        >
          GET STARTED
        </Link>
      </div>
    </nav>
  );
}
