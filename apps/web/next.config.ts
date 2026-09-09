import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Minimal-runtime production Docker image (Milestone 10): produces
  // .next/standalone, a self-contained server with only the dependencies
  // actually used, so the production image needs no full node_modules
  // install or dev server. Local `next dev` is unaffected by this option.
  output: "standalone",
};

export default nextConfig;
