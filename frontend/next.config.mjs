// import { createTranslator } from "next-intl/server";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // experimental: {
  //   serverActions: true,
  // },
  async redirects() {
    return [
      {
        source: "/",
        destination: "/login",
        permanent: false,
      },
    ];
  },
  i18n: {
    locales: ["en", "ar"],
    defaultLocale: "en",
  },
};

export default nextConfig;
