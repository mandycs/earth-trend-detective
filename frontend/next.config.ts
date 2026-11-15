import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle for the Docker image (frontend/Dockerfile).
  output: 'standalone',
  // Next 16 blocks dev resources requested from a different host name. The dev
  // server is reached as 127.0.0.1 in this project, so it has to be allowed or
  // the HMR client never loads and the page never hydrates. 100.70.153.87 is the
  // Tailscale address the demo machine serves on: without it, a dev server opened
  // there renders the page but every button stays dead (Investigate stays disabled).
  allowedDevOrigins: ['127.0.0.1', 'localhost', '100.70.153.87'],
};

export default nextConfig;
