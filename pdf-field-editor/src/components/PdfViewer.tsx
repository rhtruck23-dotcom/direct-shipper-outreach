import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { FileUp } from 'lucide-react';
import { useEditorStore } from '@/store/useEditorStore';
import { PageCanvas } from '@/components/PageCanvas';
import { openPdfDocument } from '@/lib/pdfLoader';

/** Base CSS px per PDF point at 100% zoom. */
const BASE_SCALE = 1.25;

export function PdfViewer() {
  const documentMeta = useEditorStore((s) => s.document);
  const zoom = useEditorStore((s) => s.zoom);
  const currentPageIndex = useEditorStore((s) => s.currentPageIndex);
  const [pdfjsDoc, setPdfjsDoc] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());

  useEffect(() => {
    let cancelled = false;
    let docRef: PDFDocumentProxy | null = null;

    (async () => {
      if (!documentMeta) {
        setPdfjsDoc(null);
        return;
      }
      setError(null);
      try {
        const doc = await openPdfDocument(documentMeta.pdfBytes);
        if (cancelled) {
          doc.destroy();
          return;
        }
        docRef = doc;
        setPdfjsDoc(doc);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load PDF');
          setPdfjsDoc(null);
        }
      }
    })();

    return () => {
      cancelled = true;
      docRef?.destroy();
    };
  }, [documentMeta]);

  useEffect(() => {
    const el = pageRefs.current.get(currentPageIndex);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [currentPageIndex]);

  if (!documentMeta) {
    return (
      <div
        className="flex h-full min-h-[420px] flex-col items-center justify-center gap-4 bg-slate-100 px-6 text-center text-slate-700"
        data-testid="pdf-viewer-empty"
      >
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-white shadow-sm ring-1 ring-slate-200">
          <FileUp className="h-8 w-8 text-blue-600" aria-hidden />
        </div>
        <div className="space-y-1">
          <p className="text-xl font-semibold text-slate-900">Upload a PDF</p>
          <p className="max-w-md text-sm text-slate-600">
            Use <span className="font-medium">Upload PDF</span> in the toolbar to place text, date,
            signature, typewriter, and redaction fields.
          </p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="flex h-full min-h-[420px] flex-col items-center justify-center gap-2 bg-red-50 px-6 text-center text-red-700"
        data-testid="pdf-viewer-error"
      >
        <p className="font-medium">Could not render PDF preview</p>
        <p className="max-w-lg text-sm">{error}</p>
        <p className="text-xs text-red-600/80">Try re-uploading the file. If it persists, refresh the page.</p>
      </div>
    );
  }

  if (!pdfjsDoc) {
    return (
      <div
        className="flex h-full min-h-[420px] items-center justify-center bg-slate-100 text-slate-600"
        data-testid="pdf-viewer-loading"
      >
        Loading PDF…
      </div>
    );
  }

  const scale = BASE_SCALE * (zoom / 100);

  return (
    <div
      className="h-full min-h-0 overflow-auto bg-slate-200/80 px-12 py-8"
      data-testid="pdf-viewer"
    >
      <div className="mx-auto flex w-max flex-col items-start">
        {documentMeta.pages.map((page) => (
          <div
            key={page.pageIndex}
            ref={(el) => {
              if (el) pageRefs.current.set(page.pageIndex, el);
              else pageRefs.current.delete(page.pageIndex);
            }}
          >
            <PageCanvas pdfjsDoc={pdfjsDoc} page={page} scale={scale} />
          </div>
        ))}
      </div>
    </div>
  );
}
