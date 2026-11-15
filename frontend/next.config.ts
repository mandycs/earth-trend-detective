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
  images: {
    // The cover pictures come from public/sites and only change on a redeploy (which starts a fresh cache).
    minimumCacheTTL: 60 * 60 * 24 * 7,
  },
  // public/ files are not content-hashed, so they get a day of fresh cache plus a week of
  // stale-while-revalidate instead of `immutable`: a redeploy with new data shows up within a day,
  // and a repeat visit no longer revalidates every texture and layer PNG of a case.
  async headers() {
    const cached = [{ key: 'Cache-Control', value: 'public, max-age=86400, stale-while-revalidate=604800' }]
    return ['/sites/:path*', '/video/:path*', '/img/:path*', '/brand/:path*', '/deck/:path*', '/recordings/:path*'].map(
      (source) => ({ source, headers: cached }),
    )
  },
};

export default nextConfig;
