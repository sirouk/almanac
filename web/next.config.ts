import type { NextConfig } from "next";

const apiInternalUrl = process.env.ARCLINK_API_INTERNAL_URL || "http://127.0.0.1:8900";

const nextConfig: NextConfig = {
  output: "standalone",
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
