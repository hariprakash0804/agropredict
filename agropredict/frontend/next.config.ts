import type { NextConfig } from "next";

const getBackendUrl = () => {
  if (process.env.NODE_ENV !== "production") {
    return "http://localhost:8000/api";
  }
  // Production Hugging Face Space URL
  let url = process.env.BACKEND_API_URL || "https://hariprakash-a-agropredict-api.hf.space";
  url = url.trim().replace(/\/+$/, "");
  if (!url.endsWith("/api")) {
    url += "/api";
  }
  return url;
};

const nextConfig: NextConfig = {
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
