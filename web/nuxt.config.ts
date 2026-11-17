// Viewer config. Owner: Carles.
export default defineNuxtConfig({
  modules: ['@nuxt/ui'],
  css: ['~/assets/css/main.css'],
  ssr: false,
  devtools: { enabled: false },
  // match.json is tens of MB: ship gzip and brotli copies so production serves it compressed.
  nitro: { compressPublicAssets: { gzip: true, brotli: true } },
  compatibilityDate: '2025-09-01'
})
