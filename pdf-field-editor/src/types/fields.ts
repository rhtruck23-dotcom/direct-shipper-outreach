export type FieldType = 'text' | 'date' | 'signature' | 'comment';

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

export type AnyField = TextField | DateField | SignatureField | CommentField;

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
};

export const FIELD_COLORS: Record<FieldType, string> = {
  text: '#3b82f6',
  date: '#8b5cf6',
  signature: '#10b981',
  comment: '#f59e0b',
};
