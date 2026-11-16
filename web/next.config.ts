import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Arena's development preview is proxied from per-session *.e2b.app origins.
  allowedDevOrigins: ["**.e2b.app"],
  // Include the explicitly labelled local-development snapshot and dataset-specific
  // audited report artefacts in the server trace; production analytics load from private Storage.
  outputFileTracingIncludes: { "/**/*": ["./src/data/**"] },
  serverExternalPackages: [],
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
