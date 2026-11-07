import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    // MapLibre and deck.gl are ~1.1 MB each before gzip; the app itself is ~70 KB.
    chunkSizeWarningLimit: 1300,
    rolldownOptions: {
      output: {
        // Libraries change rarely; separate chunks stay cached across app releases.
        codeSplitting: {
          groups: [
            { name: "maplibre", test: /node_modules[\\/](maplibre-gl|@maplibre|react-map-gl)/ },
            { name: "deck", test: /node_modules[\\/](@deck\.gl|@luma\.gl|@math\.gl|@loaders\.gl|h3-js)/ },
            { name: "react", test: /node_modules[\\/](react|react-dom|scheduler|@tanstack|zustand)[\\/]/ },
          ],
        },
      },
    },
  },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});
