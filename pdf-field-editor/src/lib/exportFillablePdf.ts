import {
  PDFDocument,
  PDFName,
  PDFString,
  rgb,
  StandardFonts,
} from 'pdf-lib';
import type {
  AnyField,
  CommentField,
  DateField,
  SignatureField,
  TextField,
  TypewriterField,
} from '@/types/fields';

export interface ExportOptions {
  pdfBytes: Uint8Array;
  fields: AnyField[];
  fileName?: string;
}

export interface ExportResult {
  bytes: Uint8Array;
  fileName: string;
  formFieldCount: number;
}

/**
 * Embed AcroForm fields into a copy of the source PDF.
 * Text / date → text fields; signature → Sig widget (pdf-lib has no createSignature);
 * comments are drawn as sticky notes (+ text annotation).
 */
export async function exportFillablePdf(options: ExportOptions): Promise<ExportResult> {
  const { pdfBytes, fields } = options;
  const doc = await PDFDocument.load(pdfBytes.slice());
  const form = doc.getForm();
  const helvetica = await doc.embedFont(StandardFonts.Helvetica);
  const pages = doc.getPages();

  let formFieldCount = 0;
  const usedNames = new Set<string>();

  const uniqueName = (base: string): string => {
    let name = base || 'field';
    let n = 1;
    while (usedNames.has(name)) {
      name = `${base}_${n++}`;
    }
    usedNames.add(name);
    return name;
  };

  for (const field of fields) {
    const page = pages[field.pageIndex];
    if (!page) continue;

    const { x, y, width, height } = field.rect;

    if (field.type === 'text') {
      const tf = field as TextField;
      const name = uniqueName(tf.name || `text_${field.id.slice(0, 8)}`);
      const textField = form.createTextField(name);
      textField.setText(tf.defaultValue || '');
      if (tf.multiline) textField.enableMultiline();
      if (tf.required) textField.enableRequired();
      textField.addToPage(page, {
        x,
        y,
        width,
        height,
        borderWidth: 1,
        borderColor: rgb(0.23, 0.51, 0.96),
        backgroundColor: rgb(0.93, 0.95, 1),
        textColor: rgb(0, 0, 0),
        font: helvetica,
      });
      textField.setFontSize(tf.fontSize || 11);
      formFieldCount++;
    } else if (field.type === 'date') {
      const df = field as DateField;
      const name = uniqueName(df.name || `date_${field.id.slice(0, 8)}`);
      const textField = form.createTextField(name);
      textField.setText(df.defaultValue || '');
      if (df.required) textField.enableRequired();
      textField.addToPage(page, {
        x,
        y,
        width,
        height,
        borderWidth: 1,
        borderColor: rgb(0.55, 0.36, 0.96),
        backgroundColor: rgb(0.95, 0.93, 1),
        textColor: rgb(0, 0, 0),
        font: helvetica,
      });
      textField.setFontSize(df.fontSize || 11);
      formFieldCount++;
    } else if (field.type === 'signature') {
      const sf = field as SignatureField;
      const name = uniqueName(sf.name || `signature_${field.id.slice(0, 8)}`);
      addSignatureWidget(doc, page, name, { x, y, width, height });

      if (sf.imageDataUrl) {
        try {
          const pngBytes = dataUrlToBytes(sf.imageDataUrl);
          const image = await doc.embedPng(pngBytes);
          page.drawImage(image, { x, y, width, height });
        } catch {
          /* keep empty signature widget if image decode fails */
        }
      }
      formFieldCount++;
    } else if (field.type === 'comment') {
      const cf = field as CommentField;
      page.drawRectangle({
        x,
        y,
        width,
        height,
        color: rgb(1, 0.98, 0.77),
        borderColor: rgb(0.96, 0.62, 0.04),
        borderWidth: 1,
        opacity: 0.95,
      });
      const note = `${cf.author ? cf.author + ': ' : ''}${cf.text || ''}`.slice(0, 500);
      page.drawText(note, {
        x: x + 4,
        y: y + height - 12,
        size: 9,
        font: helvetica,
        color: rgb(0.2, 0.2, 0.2),
        maxWidth: width - 8,
        lineHeight: 11,
      });

      try {
        const annotDict = doc.context.obj({
          Type: 'Annot',
          Subtype: 'Text',
          Rect: [x, y, x + width, y + height],
          Contents: PDFString.of(cf.text || ''),
          T: PDFString.of(cf.author || 'Comment'),
          C: [1, 0.8, 0],
          Name: 'Comment',
          Open: false,
        });
        const annotRef = doc.context.register(annotDict);
        page.node.addAnnot(annotRef);
      } catch {
        /* annotation attach is best-effort */
      }
    } else if (field.type === 'typewriter') {
      // Burn-in text (edit-PDF path). Not an AcroForm — stamps stay on export.
      const tw = field as TypewriterField;
      const text = (tw.text || '').trim();
      if (text) {
        const size = Math.max(6, Math.min(72, tw.fontSize || 12));
        const [r, g, b] = hexToRgb(tw.color || '#111827');
        page.drawText(text, {
          x: x + 2,
          y: y + Math.max(2, (height - size) / 2),
          size,
          font: helvetica,
          color: rgb(r, g, b),
          maxWidth: Math.max(8, width - 4),
          lineHeight: size + 2,
        });
      }
    }
  }

  try {
    form.acroForm.dict.set(PDFName.of('NeedAppearances'), doc.context.obj(true));
  } catch {
    /* ignore */
  }

  const bytes = await doc.save({ updateFieldAppearances: true });
  const base = options.fileName?.replace(/\.pdf$/i, '') || 'edited';
  return {
    bytes: new Uint8Array(bytes),
    fileName: `${base}-fillable.pdf`,
    formFieldCount,
  };
}

/**
 * pdf-lib 1.17 can read signature fields but cannot create them via PDFForm.
 * Build a merged field+widget dict (FT=/Sig) and register it on the page + AcroForm.
 */
function addSignatureWidget(
  doc: PDFDocument,
  page: ReturnType<PDFDocument['getPages']>[number],
  name: string,
  rect: { x: number; y: number; width: number; height: number },
): void {
  const { x, y, width, height } = rect;
  const context = doc.context;
  const sigDict = context.obj({
    Type: 'Annot',
    Subtype: 'Widget',
    FT: 'Sig',
    T: PDFString.of(name),
    F: 4,
    P: page.ref,
    Rect: [x, y, x + width, y + height],
    MK: {
      BC: [0.06, 0.73, 0.51],
      BG: [0.9, 0.99, 0.96],
    },
  });
  const sigRef = context.register(sigDict);
  page.node.addAnnot(sigRef);

  const form = doc.getForm();
  const fieldEntries = form.acroForm.getFields();
  const fieldRefs = fieldEntries.map(([, ref]) => ref);
  form.acroForm.dict.set(PDFName.of('Fields'), context.obj([...fieldRefs, sigRef]));
}

function hexToRgb(hex: string): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec((hex || '').trim());
  if (!m) return [0.07, 0.09, 0.15];
  const n = parseInt(m[1], 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

function dataUrlToBytes(dataUrl: string): Uint8Array {
  const match = /^data:([^;]+);base64,(.+)$/.exec(dataUrl);
  if (!match) {
    throw new Error('Invalid data URL');
  }
  const binary = atob(match[2]);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

export async function downloadBytes(bytes: Uint8Array, fileName: string): Promise<void> {
  const blob = new Blob([bytes], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.click();
  URL.revokeObjectURL(url);
}
