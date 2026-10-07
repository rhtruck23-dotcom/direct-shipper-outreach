import type { PdfRect, ScreenRect } from '@/types/fields';

/**
 * PDF user space: origin bottom-left, Y increases upward (points).
 * Screen space: origin top-left, Y increases downward (CSS px at current scale).
 *
 * scale = CSS pixels per PDF point (zoom factor applied to base render scale).
 */

export function pdfRectToScreen(
  rect: PdfRect,
  pageHeightPt: number,
  scale: number,
): ScreenRect {
  return {
    x: rect.x * scale,
    y: (pageHeightPt - rect.y - rect.height) * scale,
    width: rect.width * scale,
    height: rect.height * scale,
  };
}

export function screenRectToPdf(
  rect: ScreenRect,
  pageHeightPt: number,
  scale: number,
): PdfRect {
  const width = rect.width / scale;
  const height = rect.height / scale;
  const x = rect.x / scale;
  const y = pageHeightPt - rect.y / scale - height;
  return { x, y, width, height };
}

/** Clamp a PDF rect so it stays fully inside the page. */
export function clampPdfRect(
  rect: PdfRect,
  pageWidthPt: number,
  pageHeightPt: number,
): PdfRect {
  const width = Math.min(Math.max(rect.width, 8), pageWidthPt);
  const height = Math.min(Math.max(rect.height, 8), pageHeightPt);
  const x = Math.min(Math.max(rect.x, 0), pageWidthPt - width);
  const y = Math.min(Math.max(rect.y, 0), pageHeightPt - height);
  return { x, y, width, height };
}

export function roundTripError(
  original: PdfRect,
  pageHeightPt: number,
  scale: number,
): number {
  const screen = pdfRectToScreen(original, pageHeightPt, scale);
  const back = screenRectToPdf(screen, pageHeightPt, scale);
  return Math.max(
    Math.abs(back.x - original.x),
    Math.abs(back.y - original.y),
    Math.abs(back.width - original.width),
    Math.abs(back.height - original.height),
  );
}
