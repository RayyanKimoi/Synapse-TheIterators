/** @type {import('next').NextConfig} */
const nextConfig = {
  // Verification builds set NEXT_DIST_DIR so `next build` never overwrites the
  // dev server's .next out from under it (that is what caused the chunk 500s).
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
