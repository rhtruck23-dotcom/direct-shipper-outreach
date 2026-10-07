import * as pdfjs from 'pdfjs-dist';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist';
import type { EditorDocument, PageInfo } from '@/types/fields';

// Vite-friendly worker URL for pdfjs-dist 4.x
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

export interface LoadedPdf {
  document: EditorDocument;
  pdfjsDoc: PDFDocumentProxy;
}

export async function loadPdfFromFile(file: File): Promise<LoadedPdf> {
  const buffer = await file.arrayBuffer();
  return loadPdfFromBytes(new Uint8Array(buffer), file.name);
}

export async function loadPdfFromBytes(
  bytes: Uint8Array,
  fileName: string,
): Promise<LoadedPdf> {
  const copy = bytes.slice();
  const pdfjsDoc = await pdfjs.getDocument({ data: copy.slice() }).promise;
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
  const context = canvas.getContext('2d');
  if (!context) {
    throw new Error('Could not get 2D canvas context');
  }

  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.style.width = `${viewport.width}px`;
  canvas.style.height = `${viewport.height}px`;

  await page.render({
    canvasContext: context,
    viewport,
  }).promise;

  return { width: viewport.width, height: viewport.height };
}

export { pdfjs };
