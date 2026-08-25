const createNextIntlPlugin = require('next-intl/plugin');

// Ścieżka domyślna (`./src/i18n/request.ts`) — podana wprost, żeby przeniesienie
// pliku nie kończyło się interfejsem bez tekstów, tylko błędem przy budowie.
const withNextIntl = createNextIntlPlugin('./src/i18n/request.ts');

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  images: {
    unoptimized: true,
  },
  trailingSlash: false,
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000',
  },
}

module.exports = withNextIntl(nextConfig);
