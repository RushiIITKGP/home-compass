import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Allow opening the dev server from other devices on the LAN
  // (e.g. your phone) via this machine's IP.
  allowedDevOrigins: ["192.168.1.176"],
};

export default nextConfig;
