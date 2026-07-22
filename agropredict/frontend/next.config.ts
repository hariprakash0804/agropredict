import type { NextConfig } from "next";

const getBackendUrl = () => {
  if (process.env.NODE_ENV !== "production") {
    return "http://localhost:8000/api";
  }
  // Production Render Backend URL (configured via BACKEND_API_URL env variable in Vercel)
  let url = process.env.BACKEND_API_URL || "";
  url = url.trim().replace(/\/+$/, "");
  if (!url.endsWith("/api")) {
    url += "/api";
  }
  return url;
};

import path from "path";

const nextConfig: NextConfig = {
  experimental: {
    turbopack: {
      root: path.resolve(__dirname),
    },
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${getBackendUrl()}/:path*`,
      },
    ];
  },
};

export default nextConfig;
