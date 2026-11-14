import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Next 16 blocks dev resources requested from a different host name. The dev
  // server is reached as 127.0.0.1 in this project, so it has to be allowed or
  // the HMR client never loads and the page never hydrates.
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
};

export default nextConfig;
