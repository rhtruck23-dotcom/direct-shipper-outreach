import { inflateSync } from 'node:zlib';
import { describe, expect, it } from 'vitest';
import { PDFDocument } from 'pdf-lib';
import { exportFillablePdf, redactionRgb } from '@/lib/exportFillablePdf';
import type { AnyField } from '@/types/fields';

/** Inflate FlateDecode streams so we can assert burned-in draw ops. */
function inflatedPdfStreams(bytes: Uint8Array): string {
  const raw = Buffer.from(bytes);
  const chunks: string[] = [];
  let i = 0;
  while (i < raw.length) {
    const start = raw.indexOf(Buffer.from('stream\n'), i);
    if (start < 0) break;
    const dataStart = start + 'stream\n'.length;
    const end = raw.indexOf(Buffer.from('\nendstream'), dataStart);
    if (end < 0) break;
    const compressed = raw.subarray(dataStart, end);
    try {
      chunks.push(inflateSync(compressed).toString('latin1'));
    } catch {
      /* not zlib / already raw */
    }
    i = end + 1;
  }
  return chunks.join('\n');
}

async function blankPdfBytes(): Promise<Uint8Array> {
  const doc = await PDFDocument.create();
  doc.addPage([612, 792]);
  doc.addPage([612, 792]);
  return new Uint8Array(await doc.save());
}

describe('exportFillablePdf', () => {
  it('embeds AcroForm fields readable by pdf-lib', async () => {
    const pdfBytes = await blankPdfBytes();
    const fields: AnyField[] = [
      {
        id: 't1',
        type: 'text',
        pageIndex: 0,
        rect: { x: 50, y: 700, width: 160, height: 24 },
        name: 'ShipperName',
        required: true,
        defaultValue: 'LogixTrek',
        multiline: false,
        fontSize: 11,
      },
      {
        id: 'd1',
        type: 'date',
        pageIndex: 0,
        rect: { x: 50, y: 650, width: 120, height: 24 },
        name: 'EffectiveDate',
        required: false,
        defaultValue: '2026-10-07',
        format: 'yyyy-MM-dd',
        fontSize: 11,
      },
      {
        id: 's1',
        type: 'signature',
        pageIndex: 1,
        rect: { x: 50, y: 200, width: 180, height: 60 },
        name: 'AuthSig',
        required: false,
        imageDataUrl: '',
      },
      {
        id: 'c1',
        type: 'comment',
        pageIndex: 0,
        rect: { x: 300, y: 500, width: 140, height: 70 },
        name: 'Note1',
        required: false,
        text: 'Review clause 3',
        author: 'QA',
        createdAt: new Date().toISOString(),
        color: '#fbbf24',
      },
      {
        id: 'tw1',
        type: 'typewriter',
        pageIndex: 0,
        rect: { x: 80, y: 400, width: 220, height: 28 },
        name: 'Stamp1',
        required: false,
        text: 'Burned typewriter line',
        fontSize: 12,
        color: '#111827',
      },
    ];

    const result = await exportFillablePdf({ pdfBytes, fields, fileName: 'sample.pdf' });
    expect(result.fileName).toBe('sample-fillable.pdf');
    expect(result.formFieldCount).toBe(3);
    expect(result.bytes.byteLength).toBeGreaterThan(pdfBytes.byteLength);

    const loaded = await PDFDocument.load(result.bytes);
    const form = loaded.getForm();
    const formFields = form.getFields();
    const names = formFields.map((f) => f.getName());

    expect(names).toContain('ShipperName');
    expect(names).toContain('EffectiveDate');
    expect(names).toContain('AuthSig');

    const text = form.getTextField('ShipperName');
    expect(text.getText()).toBe('LogixTrek');
    expect(text.isRequired()).toBe(true);

    const date = form.getTextField('EffectiveDate');
    expect(date.getText()).toBe('2026-10-07');

    const sig = form.getSignature('AuthSig');
    expect(sig.getName()).toBe('AuthSig');
  });

  it('burns redaction rectangles into page content (not AcroForm)', async () => {
    const pdfBytes = await blankPdfBytes();
    const fields: AnyField[] = [
      {
        id: 'r1',
        type: 'redaction',
        pageIndex: 0,
        rect: { x: 72, y: 680, width: 200, height: 24 },
        name: 'HideSSN',
        required: false,
        color: 'black',
      },
      {
        id: 'r2',
        type: 'redaction',
        pageIndex: 0,
        rect: { x: 72, y: 640, width: 120, height: 20 },
        name: 'VoidMark',
        required: false,
        color: 'void',
      },
      {
        id: 'r3',
        type: 'redaction',
        pageIndex: 0,
        rect: { x: 72, y: 600, width: 100, height: 18 },
        name: 'WhiteCover',
        required: false,
        color: 'white',
      },
      {
        id: 'r4',
        type: 'redaction',
        pageIndex: 0,
        rect: { x: 72, y: 560, width: 100, height: 18 },
        name: 'RedactRed',
        required: false,
        color: 'redact',
      },
    ];

    const result = await exportFillablePdf({ pdfBytes, fields, fileName: 'redact.pdf' });
    expect(result.formFieldCount).toBe(0);
    expect(result.bytes.byteLength).toBeGreaterThan(pdfBytes.byteLength + 80);

    const loaded = await PDFDocument.load(result.bytes);
    expect(loaded.getForm().getFields()).toHaveLength(0);

    expect(redactionRgb('black')).toEqual([0, 0, 0]);
    expect(redactionRgb('white')).toEqual([1, 1, 1]);
    expect(redactionRgb('redact')[0]).toBeGreaterThan(0.5);
    expect(redactionRgb('void')[0]).toBeGreaterThan(0.3);

    // Drawn content: solid fill rects only (no outline, no VOID/REDACT labels).
    const ops = inflatedPdfStreams(result.bytes);
    expect(ops).not.toMatch(/<564[Ff]4944>/);
    expect(ops).toMatch(/(?:^|\s)(?:f|B)(?:\s|$)/m);
    expect(ops).toMatch(/0\s+0\s+0\s+rg/);
    expect(ops).toMatch(/72\s+680/);
  });

  it('exports text/date without colored border chrome', async () => {
    const pdfBytes = await blankPdfBytes();
    const fields: AnyField[] = [
      {
        id: 't1',
        type: 'text',
        pageIndex: 0,
        rect: { x: 50, y: 700, width: 160, height: 24 },
        name: 'ShipperName',
        required: false,
        defaultValue: 'Ada',
        multiline: false,
        fontSize: 11,
      },
    ];
    const result = await exportFillablePdf({ pdfBytes, fields, fileName: 'plain.pdf' });
    const loaded = await PDFDocument.load(result.bytes);
    const text = loaded.getForm().getTextField('ShipperName');
    expect(text.getText()).toBe('Ada');
    // Appearance should not encode the old blue border RGB (0.23, 0.51, 0.96).
    const raw = Buffer.from(result.bytes).toString('latin1');
    expect(raw).not.toMatch(/0\.23\s+0\.51\s+0\.96/);
  });

  it('outreach mode burns redactions but skips AcroForm + signature stamps', async () => {
    const pdfBytes = await blankPdfBytes();
    const tinyPng =
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';
    const fields: AnyField[] = [
      {
        id: 't1',
        type: 'text',
        pageIndex: 0,
        rect: { x: 50, y: 700, width: 160, height: 24 },
        name: 'ShipperName',
        required: false,
        defaultValue: 'SkipMe',
        multiline: false,
        fontSize: 11,
      },
      {
        id: 's1',
        type: 'signature',
        pageIndex: 0,
        rect: { x: 50, y: 200, width: 180, height: 60 },
        name: 'AuthSig',
        required: false,
        imageDataUrl: tinyPng,
      },
      {
        id: 'r1',
        type: 'redaction',
        pageIndex: 0,
        rect: { x: 72, y: 680, width: 200, height: 24 },
        name: 'HideSSN',
        required: false,
        color: 'black',
      },
    ];
    const result = await exportFillablePdf({
      pdfBytes,
      fields,
      fileName: 'outreach.pdf',
      includeFormFields: false,
      stampSignatures: false,
    });
    expect(result.formFieldCount).toBe(0);
    const loaded = await PDFDocument.load(result.bytes);
    expect(loaded.getForm().getFields()).toHaveLength(0);
    const ops = inflatedPdfStreams(result.bytes);
    expect(ops).toMatch(/0\s+0\s+0\s+rg/);
  });
});
