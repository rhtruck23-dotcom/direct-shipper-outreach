import { describe, expect, it } from 'vitest';
import { PDFDocument } from 'pdf-lib';
import { exportFillablePdf } from '@/lib/exportFillablePdf';
import type { AnyField } from '@/types/fields';

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
});
