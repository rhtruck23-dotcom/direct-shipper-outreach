import { describe, expect, it } from 'vitest';
import {
  clampPdfRect,
  pdfRectToScreen,
  roundTripError,
  screenRectToPdf,
} from '@/lib/coordinateUtils';

describe('coordinateUtils', () => {
  const pageHeight = 792;
  const scales = [0.5, 1, 1.25, 2, 3];

  it('round-trips PDF ↔ screen within ±0.5pt for common scales', () => {
    const rects = [
      { x: 50, y: 100, width: 160, height: 24 },
      { x: 0, y: 0, width: 10, height: 10 },
      { x: 400, y: 700, width: 180, height: 60 },
      { x: 12.5, y: 333.25, width: 99.75, height: 40.5 },
    ];

    for (const scale of scales) {
      for (const rect of rects) {
        const err = roundTripError(rect, pageHeight, scale);
        expect(err, `scale=${scale} rect=${JSON.stringify(rect)}`).toBeLessThanOrEqual(0.5);
      }
    }
  });

  it('flips Y correctly (bottom-left PDF → top-left screen)', () => {
    const rect = { x: 10, y: 0, width: 20, height: 30 };
    const screen = pdfRectToScreen(rect, pageHeight, 1);
    // y=0 bottom in PDF → top of rect is at pageHeight - 0 - 30
    expect(screen.y).toBe(pageHeight - 30);
    expect(screen.x).toBe(10);
    expect(screen.width).toBe(20);
    expect(screen.height).toBe(30);
  });

  it('inverse of pdfRectToScreen is screenRectToPdf', () => {
    const original = { x: 72, y: 200, width: 120, height: 36 };
    const scale = 1.5;
    const screen = pdfRectToScreen(original, pageHeight, scale);
    const back = screenRectToPdf(screen, pageHeight, scale);
    expect(Math.abs(back.x - original.x)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(back.y - original.y)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(back.width - original.width)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(back.height - original.height)).toBeLessThanOrEqual(0.5);
  });

  it('clampPdfRect keeps field inside page', () => {
    const clamped = clampPdfRect(
      { x: -20, y: -10, width: 700, height: 900 },
      612,
      792,
    );
    expect(clamped.x).toBeGreaterThanOrEqual(0);
    expect(clamped.y).toBeGreaterThanOrEqual(0);
    expect(clamped.x + clamped.width).toBeLessThanOrEqual(612);
    expect(clamped.y + clamped.height).toBeLessThanOrEqual(792);
  });
});
