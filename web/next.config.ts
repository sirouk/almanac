import type { NextConfig } from "next";

const apiInternalUrl = process.env.ARCLINK_API_INTERNAL_URL || "http://127.0.0.1:8900";

// Conservative, app-aware Content-Security-Policy.
//
// The app talks to its own API via same-origin /api/v1/* rewrites (connect-src
// 'self'), renders Tailwind/Next inline <style> blocks (style-src needs
// 'unsafe-inline'), and relies on Next.js App Router inline bootstrap scripts
// (script-src needs 'unsafe-inline'). Checkout is a top-level navigation/anchor
// to Stripe (covered by form-action, not connect/script). Stripe is permitted
// as a connect/frame/form target so an embedded Stripe.js path stays unbroken
// if it is ever added.
const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  "script-src 'self' 'unsafe-inline' https://js.stripe.com",
  "connect-src 'self' https://api.stripe.com",
  "frame-src 'self' https://js.stripe.com https://checkout.stripe.com",
  "form-action 'self' https://checkout.stripe.com https://billing.stripe.com",
  "frame-ancestors 'none'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${apiInternalUrl}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
