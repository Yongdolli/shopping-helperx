import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      strategies: "injectManifest",   // src/sw.ts 를 직접 사용 (푸시 수신 때문)
      srcDir: "src",
      filename: "sw.ts",
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      injectManifest: { globPatterns: ["**/*.{js,css,html,svg,png,woff2}"] },
      manifest: {
        name: "Shopping Helper",
        short_name: "ShopHelper",
        description: "한·중·미 쇼핑몰 가격 급락 알림",
        theme_color: "#0f172a",
        background_color: "#0f172a",
        display: "standalone",
        lang: "ko",
        start_url: "/",
        share_target: { action: "/share", method: "GET", params: { title: "title", text: "text", url: "url" } },
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      },
    }),
  ],
});
