export type FieldType =
  | 'text'
  | 'date'
  | 'signature'
  | 'comment'
  | 'typewriter'
  | 'redaction';

/** Solid redaction fill presets (burned into PDF on export — not Gaussian blur). */
export type RedactionColor = 'black' | 'white' | 'void' | 'redact';

/** PDF user-space rectangle: origin bottom-left, Y up. Units = PDF points. */
export interface PdfRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** Screen-space rectangle: origin top-left, Y down. Units = CSS pixels at current zoom. */
export interface ScreenRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface FieldBase {
  id: string;
  type: FieldType;
  pageIndex: number;
  /** PDF user-space rect (bottom-left origin). */
  rect: PdfRect;
  name: string;
  required: boolean;
}

export interface TextField extends FieldBase {
  type: 'text';
  defaultValue: string;
  multiline: boolean;
  fontSize: number;
}

export interface DateField extends FieldBase {
  type: 'date';
  /** ISO date string YYYY-MM-DD or empty. */
  defaultValue: string;
  format: string;
  fontSize: number;
}

export interface SignatureField extends FieldBase {
  type: 'signature';
  /** Data URL of drawn signature, or empty if not yet signed. */
  imageDataUrl: string;
}

export interface CommentField extends FieldBase {
  type: 'comment';
  text: string;
  author: string;
  /** ISO timestamp. */
  createdAt: string;
  color: string;
}

/** Free text stamped onto the page on export (edit-PDF path via pdf-lib drawText). */
export interface TypewriterField extends FieldBase {
  type: 'typewriter';
  text: string;
  fontSize: number;
  color: string;
}

/** Opaque rectangle covering sensitive content (burned in on export). */
export interface RedactionField extends FieldBase {
  type: 'redaction';
  color: RedactionColor;
}

export type AnyField =
  | TextField
  | DateField
  | SignatureField
  | CommentField
  | TypewriterField
  | RedactionField;

export type PlacementMode = FieldType | null;

export interface PageInfo {
  pageIndex: number;
  widthPt: number;
  heightPt: number;
}

export interface EditorDocument {
  fileName: string;
  /** Original PDF bytes. */
  pdfBytes: Uint8Array;
  pageCount: number;
  pages: PageInfo[];
}

export const DEFAULT_FIELD_SIZES: Record<FieldType, { width: number; height: number }> = {
  text: { width: 160, height: 24 },
  date: { width: 120, height: 24 },
  signature: { width: 180, height: 60 },
  comment: { width: 160, height: 80 },
  typewriter: { width: 200, height: 28 },
  redaction: { width: 160, height: 28 },
};

export const FIELD_COLORS: Record<FieldType, string> = {
  text: '#3b82f6',
  date: '#8b5cf6',
  signature: '#10b981',
  comment: '#f59e0b',
  typewriter: '#0f766e',
  redaction: '#64748b',
};

export const REDACTION_COLOR_OPTIONS: {
  value: RedactionColor;
  label: string;
  fill: string;
}[] = [
  { value: 'black', label: 'Black', fill: '#000000' },
  { value: 'white', label: 'White', fill: '#ffffff' },
  { value: 'void', label: 'Void', fill: '#6b7280' },
  { value: 'redact', label: 'Redact', fill: '#b91c1c' },
];

export function redactionFillHex(color: RedactionColor): string {
  return REDACTION_COLOR_OPTIONS.find((o) => o.value === color)?.fill ?? '#000000';
}
