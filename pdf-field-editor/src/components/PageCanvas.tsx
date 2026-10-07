import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import type { FieldType, PageInfo, PdfRect } from '@/types/fields';
import { renderPageToCanvas } from '@/lib/pdfLoader';
import { screenRectToPdf } from '@/lib/coordinateUtils';
import { useEditorStore } from '@/store/useEditorStore';
import { FieldOverlay } from '@/components/FieldOverlay';

interface PageCanvasProps {
  pdfjsDoc: PDFDocumentProxy;
  page: PageInfo;
  scale: number;
}

interface DragDraft {
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
}

export function PageCanvas({ pdfjsDoc, page, scale }: PageCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [rendering, setRendering] = useState(true);
  const [draft, setDraft] = useState<DragDraft | null>(null);
  const placementMode = useEditorStore((s) => s.placementMode);
  const fields = useEditorStore((s) => s.fields.filter((f) => f.pageIndex === page.pageIndex));
  const addField = useEditorStore((s) => s.addField);
  const selectField = useEditorStore((s) => s.selectField);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setRendering(true);
      try {
        const pdfPage = await pdfjsDoc.getPage(page.pageIndex + 1);
        if (!canvasRef.current || cancelled) return;
        await renderPageToCanvas(pdfPage, canvasRef.current, scale);
      } finally {
        if (!cancelled) setRendering(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [pdfjsDoc, page.pageIndex, scale]);

  const toLocal = useCallback((clientX: number, clientY: number) => {
    const el = containerRef.current;
    if (!el) return { x: 0, y: 0 };
    const rect = el.getBoundingClientRect();
    return {
      x: Math.min(Math.max(clientX - rect.left, 0), rect.width),
      y: Math.min(Math.max(clientY - rect.top, 0), rect.height),
    };
  }, []);

  const onPointerDown = useCallback(
    (e: ReactPointerEvent) => {
      if (!placementMode || e.button !== 0) return;
      e.preventDefault();
      const { x, y } = toLocal(e.clientX, e.clientY);
      setDraft({ startX: x, startY: y, currentX: x, currentY: y });
      (e.target as HTMLElement).setPointerCapture?.(e.pointerId);
    },
    [placementMode, toLocal],
  );

  const onPointerMove = useCallback(
    (e: ReactPointerEvent) => {
      if (!draft) return;
      const { x, y } = toLocal(e.clientX, e.clientY);
      setDraft({ ...draft, currentX: x, currentY: y });
    },
    [draft, toLocal],
  );

  const finishPlacement = useCallback(
    (mode: FieldType, draftRect: DragDraft) => {
      const x = Math.min(draftRect.startX, draftRect.currentX);
      const y = Math.min(draftRect.startY, draftRect.currentY);
      const width = Math.abs(draftRect.currentX - draftRect.startX);
      const height = Math.abs(draftRect.currentY - draftRect.startY);

      // Click without drag → place default-sized field at click point
      const screenRect =
        width < 4 || height < 4
          ? { x, y, width: 0, height: 0 }
          : { x, y, width, height };

      let pdf: PdfRect;
      if (screenRect.width === 0 || screenRect.height === 0) {
        // Convert click point; store will apply default size
        const point = screenRectToPdf(
          { x, y, width: 1, height: 1 },
          page.heightPt,
          scale,
        );
        pdf = { x: point.x, y: point.y, width: 0, height: 0 };
      } else {
        pdf = screenRectToPdf(screenRect, page.heightPt, scale);
      }
      addField(mode, page.pageIndex, pdf);
    },
    [addField, page.heightPt, page.pageIndex, scale],
  );

  const onPointerUp = useCallback(
    (e: ReactPointerEvent) => {
      if (!draft || !placementMode) {
        setDraft(null);
        return;
      }
      finishPlacement(placementMode, draft);
      setDraft(null);
      try {
        (e.target as HTMLElement).releasePointerCapture?.(e.pointerId);
      } catch {
        /* ignore */
      }
    },
    [draft, finishPlacement, placementMode],
  );

  const draftStyle = (() => {
    if (!draft) return null;
    const left = Math.min(draft.startX, draft.currentX);
    const top = Math.min(draft.startY, draft.currentY);
    const width = Math.abs(draft.currentX - draft.startX);
    const height = Math.abs(draft.currentY - draft.startY);
    return { left, top, width, height };
  })();

  return (
    <div
      className="relative mb-6 inline-block shadow-lg ring-1 ring-slate-300"
      data-testid={`page-canvas-${page.pageIndex}`}
      data-page-index={page.pageIndex}
    >
      <div
        ref={containerRef}
        className="relative touch-none"
        style={{
          width: page.widthPt * scale,
          height: page.heightPt * scale,
          cursor: placementMode ? 'crosshair' : 'default',
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onClick={() => {
          if (!placementMode) selectField(null);
        }}
      >
        <canvas ref={canvasRef} className="block" />
        {rendering && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/60 text-sm text-slate-600">
            Rendering page {page.pageIndex + 1}…
          </div>
        )}
        {fields.map((field) => (
          <FieldOverlay key={field.id} field={field} page={page} scale={scale} />
        ))}
        {draftStyle && (
          <div
            className="pointer-events-none absolute z-30 border-2 border-dashed border-blue-500 bg-blue-400/20"
            style={draftStyle}
            data-testid="placement-draft"
          />
        )}
      </div>
      <div className="absolute -left-10 top-0 rounded bg-slate-700 px-1.5 py-0.5 text-xs text-white">
        {page.pageIndex + 1}
      </div>
    </div>
  );
}
