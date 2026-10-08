import type { AnyField, EditorDocument } from '@/types/fields';
import { exportFillablePdf } from '@/lib/exportFillablePdf';

export interface OutreachFieldPayload {
  id: string;
  type: 'text' | 'date' | 'sign';
  name: string;
  label: string;
  page: number;
  x: number;
  y_from_top: number;
  w: number;
  h: number;
  value: string;
  color: string;
}

export interface SaveToOutreachPayload {
  action: 'save_to_outreach';
  nonce: string;
  title: string;
  fileName: string;
  pdfBase64: string;
  fields: OutreachFieldPayload[];
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

/** Map React fields → normalized Esign CRM fields (AcroForm types only). */
export function fieldsToOutreach(
  fields: AnyField[],
  document: EditorDocument,
): OutreachFieldPayload[] {
  const out: OutreachFieldPayload[] = [];
  for (const field of fields) {
    if (field.type !== 'text' && field.type !== 'date' && field.type !== 'signature') {
      continue;
    }
    const page = document.pages[field.pageIndex];
    if (!page || page.widthPt <= 0 || page.heightPt <= 0) continue;
    const { x, y, width, height } = field.rect;
    const xN = Math.min(0.95, Math.max(0, x / page.widthPt));
    const wN = Math.min(0.9, Math.max(0.05, width / page.widthPt));
    const hN = Math.min(0.2, Math.max(0.02, height / page.heightPt));
    const yFromTop = Math.min(
      0.95,
      Math.max(0, 1 - (y + height) / page.heightPt),
    );
    const value =
      field.type === 'text' || field.type === 'date'
        ? String(field.defaultValue || '')
        : '';
    out.push({
      id: field.id,
      type: field.type === 'signature' ? 'sign' : field.type,
      name: field.name,
      label: field.name,
      page: field.pageIndex,
      x: xN,
      y_from_top: yFromTop,
      w: wN,
      h: hN,
      value,
      color: '#111827',
    });
  }
  return out;
}

export async function buildSaveToOutreachPayload(options: {
  document: EditorDocument;
  fields: AnyField[];
  title?: string;
}): Promise<SaveToOutreachPayload> {
  const { document, fields } = options;
  const exported = await exportFillablePdf({
    pdfBytes: document.pdfBytes,
    fields,
    fileName: document.fileName,
  });
  const title =
    (options.title || '').trim() ||
    document.fileName.replace(/\.pdf$/i, '') ||
    'Agreement';
  return {
    action: 'save_to_outreach',
    nonce: `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`,
    title,
    fileName: document.fileName,
    pdfBase64: bytesToBase64(exported.bytes),
    fields: fieldsToOutreach(fields, document),
  };
}

/** Post save payload to Streamlit parent via setComponentValue (no-op standalone). */
export function postSaveToOutreach(payload: SaveToOutreachPayload): boolean {
  const st = window.Streamlit;
  if (!st || typeof st.setComponentValue !== 'function') {
    return false;
  }
  st.setComponentValue(payload);
  return true;
}

declare global {
  interface Window {
    Streamlit?: {
      setComponentValue: (value: unknown) => void;
      setFrameHeight?: (height: number) => void;
      setComponentReady?: () => void;
    };
  }
}
