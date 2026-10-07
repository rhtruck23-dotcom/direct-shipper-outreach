import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import fs from 'fs';

/** Inject Streamlit iframe bridge into production build (no-op when standalone). */
function streamlitEmbedBridge(): Plugin {
  const bridgeFiles = [
    'streamlit-component-lib.js',
    'streamlit-frame-height.js',
  ] as const;

  return {
    name: 'streamlit-embed-bridge',
    transformIndexHtml(html) {
      const tags = bridgeFiles
        .map((f) => `<script src="./${f}"></script>`)
        .join('\n    ');
      return html.replace('</body>', `    ${tags}\n  </body>`);
    },
    closeBundle() {
      const outDir = path.resolve(__dirname, 'dist');
      const scriptsDir = path.resolve(__dirname, 'scripts');
      const libSrc = path.resolve(
        __dirname,
        '../src/esign_placer/frontend/streamlit-component-lib.js',
      );

      if (!fs.existsSync(outDir)) return;

      // Prefer esign_placer copy of Streamlit component lib; fall back to scripts/
      const libDest = path.join(outDir, 'streamlit-component-lib.js');
      if (fs.existsSync(libSrc)) {
        fs.copyFileSync(libSrc, libDest);
      } else {
        const alt = path.join(scriptsDir, 'streamlit-component-lib.js');
        if (fs.existsSync(alt)) fs.copyFileSync(alt, libDest);
      }

      const heightSrc = path.join(scriptsDir, 'streamlit-frame-height.js');
      if (fs.existsSync(heightSrc)) {
        fs.copyFileSync(heightSrc, path.join(outDir, 'streamlit-frame-height.js'));
      }

      // Sync into Streamlit package so Cloud serves the SPA from the same app.
      const embedDir = path.resolve(__dirname, '../src/pdf_field_editor/frontend');
      fs.mkdirSync(embedDir, { recursive: true });
      fs.cpSync(outDir, embedDir, { recursive: true });
    },
  };
}

export default defineConfig({
  // Relative asset URLs so Streamlit's /component/.../index.html can load JS/CSS.
  base: './',
  plugins: [react(), streamlitEmbedBridge()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  optimizeDeps: {
    include: ['pdfjs-dist'],
  },
  worker: {
    format: 'es',
  },
});
