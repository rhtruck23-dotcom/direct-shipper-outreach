import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { useEditorStore } from '@/store/useEditorStore';
import { PageCanvas } from '@/components/PageCanvas';
import { pdfjs } from '@/lib/pdfLoader';

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
    let loadingTask: ReturnType<typeof pdfjs.getDocument> | null = null;

    (async () => {
      if (!documentMeta) {
        setPdfjsDoc(null);
        return;
      }
      setError(null);
      try {
        loadingTask = pdfjs.getDocument({ data: documentMeta.pdfBytes.slice() });
        const doc = await loadingTask.promise;
        if (cancelled) {
          doc.destroy();
          return;
        }
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
      loadingTask?.destroy();
    };
  }, [documentMeta]);

  useEffect(() => {
    const el = pageRefs.current.get(currentPageIndex);
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [currentPageIndex]);

  if (!documentMeta) {
    return (
      <div
        className="flex h-full flex-col items-center justify-center gap-3 bg-slate-100 text-slate-600"
        data-testid="pdf-viewer-empty"
      >
        <p className="text-lg font-medium">No PDF loaded</p>
        <p className="text-sm">
          Upload a PDF to place text, date, signature, comment, typewriter, and redaction fields.
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center bg-red-50 text-red-700" data-testid="pdf-viewer-error">
        {error}
      </div>
    );
  }

  if (!pdfjsDoc) {
    return (
      <div className="flex h-full items-center justify-center bg-slate-100 text-slate-600" data-testid="pdf-viewer-loading">
        Loading PDF…
      </div>
    );
  }

  const scale = BASE_SCALE * (zoom / 100);

  return (
    <div
      className="h-full overflow-auto bg-slate-200/80 px-12 py-8"
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
