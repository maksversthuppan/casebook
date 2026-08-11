import type { NextConfig } from "next";

const backend = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Standalone output is what the Tauri sidecar runs from (docs/desktop-app-roadmap.md
  // Phase A/C) — a self-contained server.js plus a pruned node_modules, no full
  // `next start` install required on the machine it runs on.
  output: "standalone",
  // The API is proxied rather than called cross-origin, so the browser sees one
  // origin and the session cookie needs no CORS or SameSite special-casing. On
  // the office server the same arrangement serves both from one host.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
