import * as pdfjs from 'pdfjs-dist';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';
import type { EditorDocument, PageInfo } from '@/types/fields';

/**
 * PDF.js worker for Streamlit custom-component iframes.
 *
 * Streamlit may serve `.mjs` with a bad Content-Type, or browsers may block
 * cross-origin module workers. Prefer a same-origin hashed asset, re-wrap as a
 * blob URL (correct MIME), then fall back to CDN.
 */
function viteWorkerUrl(): string {
  // Static string required — Vite rewrites this to ./assets/pdf.worker.min-<hash>.mjs
  return new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();
}

function cdnWorkerUrl(): string {
  return `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;
}


let workerReady: Promise<string> | null = null;

async function tryBlobWorker(src: string): Promise<string | null> {
  try {
    const res = await fetch(src, { cache: 'force-cache' });
    if (!res.ok) return null;
    const buf = await res.arrayBuffer();
    if (buf.byteLength < 1000) return null;
    const blob = new Blob([buf], { type: 'text/javascript' });
    return URL.createObjectURL(blob);
  } catch {
    return null;
  }
}

/** Resolve and assign GlobalWorkerOptions.workerSrc (idempotent). */
export async function ensurePdfWorker(): Promise<string> {
  if (!workerReady) {
    workerReady = (async () => {
      const candidates = [viteWorkerUrl(), cdnWorkerUrl()];

      for (const src of candidates) {
        const blobUrl = await tryBlobWorker(src);
        if (blobUrl) {
          pdfjs.GlobalWorkerOptions.workerSrc = blobUrl;
          return blobUrl;
        }
      }

      // Direct URLs as last resort (CDN may work when fetch of local failed)
      const fallback = cdnWorkerUrl();
      pdfjs.GlobalWorkerOptions.workerSrc = fallback;
      return fallback;
    })();
  }
  return workerReady;
}

// Synchronous best-effort so first paint has a workerSrc before async ensure.
pdfjs.GlobalWorkerOptions.workerSrc = viteWorkerUrl();

export interface LoadedPdf {
  document: EditorDocument;
  pdfjsDoc: PDFDocumentProxy;
}

const DOC_OPTS = {
  // Sandboxed Streamlit iframes often block eval used by some font paths.
  isEvalSupported: false,
  useSystemFonts: true,
} as const;

export async function loadPdfFromFile(file: File): Promise<LoadedPdf> {
  const buffer = await file.arrayBuffer();
  return loadPdfFromBytes(new Uint8Array(buffer), file.name);
}

export async function openPdfDocument(data: Uint8Array): Promise<PDFDocumentProxy> {
  await ensurePdfWorker();
  try {
    return await pdfjs.getDocument({ data: data.slice(), ...DOC_OPTS }).promise;
  } catch (first) {
    // Blob worker can fail in some embeds — retry with direct CDN module URL.
    pdfjs.GlobalWorkerOptions.workerSrc = cdnWorkerUrl();
    try {
      return await pdfjs.getDocument({ data: data.slice(), ...DOC_OPTS }).promise;
    } catch {
      throw first instanceof Error ? first : new Error('Failed to open PDF');
    }
  }
}

export async function loadPdfFromBytes(
  bytes: Uint8Array,
  fileName: string,
): Promise<LoadedPdf> {
  const copy = bytes.slice();
  const pdfjsDoc = await openPdfDocument(copy);
  const pages: PageInfo[] = [];

  for (let i = 1; i <= pdfjsDoc.numPages; i++) {
    const page = await pdfjsDoc.getPage(i);
    const viewport = page.getViewport({ scale: 1 });
    pages.push({
      pageIndex: i - 1,
      widthPt: viewport.width,
      heightPt: viewport.height,
    });
  }

  return {
    document: {
      fileName,
      pdfBytes: copy,
      pageCount: pdfjsDoc.numPages,
      pages,
    },
    pdfjsDoc,
  };
}

export async function renderPageToCanvas(
  page: PDFPageProxy,
  canvas: HTMLCanvasElement,
  scale: number,
): Promise<{ width: number; height: number }> {
  const viewport = page.getViewport({ scale });
  const context = canvas.getContext('2d', { alpha: false });
  if (!context) {
    throw new Error('Could not get 2D canvas context');
  }

  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.style.width = `${viewport.width}px`;
  canvas.style.height = `${viewport.height}px`;

  // White page background so blank-looking PDFs still show a page plane
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, canvas.width, canvas.height);

  await page.render({
    canvasContext: context,
    viewport,
  }).promise;

  return { width: viewport.width, height: viewport.height };
}

export { pdfjs };
