import Image from "next/image";
import Link from "next/link";

export default function MarketingFooter() {
  return (
    <footer className="border-t border-white/5 bg-[#080808] py-12">
      <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-6 px-6 md:flex-row lg:px-8">
        <Link href="/" className="flex items-center" aria-label="ArcLink home">
          <Image
            src="/marketing/Arclink_v3--orange_symbol_white_text.svg"
            alt="ArcLink"
            width={135}
            height={28}
            className="h-7 w-auto"
          />
        </Link>
        <div className="flex flex-wrap items-center justify-center gap-6">
          <Link href="/privacy" className="font-body text-xs text-[#E7E6E6]/25 transition-colors hover:text-[#E7E6E6]/50">
            Privacy Policy
          </Link>
          <Link href="/terms" className="font-body text-xs text-[#E7E6E6]/25 transition-colors hover:text-[#E7E6E6]/50">
            Terms of Service
          </Link>
          <Link href="/refunds" className="font-body text-xs text-[#E7E6E6]/25 transition-colors hover:text-[#E7E6E6]/50">
            Refund Policy
          </Link>
        </div>
        <p className="font-body text-xs text-[#E7E6E6]/20">
          &copy; {new Date().getFullYear()} ArcLink. Built by ArcLink. Run by Raven.
        </p>
      </div>
    </footer>
  );
}
