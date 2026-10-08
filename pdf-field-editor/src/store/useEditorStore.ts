import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import { enableMapSet } from 'immer';
import { format } from 'date-fns';
import type {
  AnyField,
  CommentField,
  DateField,
  EditorDocument,
  FieldType,
  PdfRect,
  PlacementMode,
  SignatureField,
  TextField,
  TypewriterField,
} from '@/types/fields';
import { DEFAULT_FIELD_SIZES } from '@/types/fields';
import { clampPdfRect } from '@/lib/coordinateUtils';
import { createId } from '@/lib/uuid';

enableMapSet();

const MAX_HISTORY = 50;

export interface EditorState {
  document: EditorDocument | null;
  fields: AnyField[];
  selectedFieldId: string | null;
  placementMode: PlacementMode;
  zoom: number;
  currentPageIndex: number;
  past: AnyField[][];
  future: AnyField[][];
  signatureModalFieldId: string | null;
  isDirty: boolean;

  setDocument: (doc: EditorDocument | null) => void;
  setZoom: (zoom: number) => void;
  setCurrentPage: (pageIndex: number) => void;
  setPlacementMode: (mode: PlacementMode) => void;
  selectField: (id: string | null) => void;

  addField: (type: FieldType, pageIndex: number, rect: PdfRect) => string;
  updateField: (id: string, patch: Partial<AnyField>) => void;
  updateFieldRect: (id: string, rect: PdfRect) => void;
  deleteField: (id: string) => void;
  deleteSelected: () => void;

  openSignatureModal: (fieldId: string) => void;
  closeSignatureModal: () => void;
  applySignature: (fieldId: string, imageDataUrl: string) => void;

  undo: () => void;
  redo: () => void;
  canUndo: () => boolean;
  canRedo: () => boolean;

  reset: () => void;
  getFieldsForPage: (pageIndex: number) => AnyField[];
}

function cloneFields(fields: AnyField[]): AnyField[] {
  // Avoid structuredClone — Immer drafts / proxies are not cloneable.
  return JSON.parse(JSON.stringify(fields)) as AnyField[];
}

function pushHistory(state: { past: AnyField[][]; future: AnyField[][]; fields: AnyField[] }) {
  state.past.push(cloneFields(state.fields));
  if (state.past.length > MAX_HISTORY) {
    state.past.shift();
  }
  state.future = [];
}

function createField(
  type: FieldType,
  pageIndex: number,
  rect: PdfRect,
): AnyField {
  const id = createId();
  const base = {
    id,
    pageIndex,
    rect,
    required: false,
  };

  switch (type) {
    case 'text':
      return {
        ...base,
        type: 'text',
        name: `Text_${id.slice(0, 6)}`,
        defaultValue: '',
        multiline: false,
        fontSize: 11,
      } satisfies TextField;
    case 'date':
      return {
        ...base,
        type: 'date',
        name: `Date_${id.slice(0, 6)}`,
        defaultValue: format(new Date(), 'yyyy-MM-dd'),
        format: 'yyyy-MM-dd',
        fontSize: 11,
      } satisfies DateField;
    case 'signature':
      return {
        ...base,
        type: 'signature',
        name: `Signature_${id.slice(0, 6)}`,
        imageDataUrl: '',
      } satisfies SignatureField;
    case 'comment':
      return {
        ...base,
        type: 'comment',
        name: `Comment_${id.slice(0, 6)}`,
        text: '',
        author: 'Me',
        createdAt: new Date().toISOString(),
        color: '#fbbf24',
      } satisfies CommentField;
    case 'typewriter':
      return {
        ...base,
        type: 'typewriter',
        name: `Typewriter_${id.slice(0, 6)}`,
        text: '',
        fontSize: 12,
        color: '#111827',
      } satisfies TypewriterField;
  }
}

export const useEditorStore = create<EditorState>()(
  immer((set, get) => ({
    document: null,
    fields: [],
    selectedFieldId: null,
    placementMode: null,
    zoom: 100,
    currentPageIndex: 0,
    past: [],
    future: [],
    signatureModalFieldId: null,
    isDirty: false,

    setDocument: (doc) =>
      set((state) => {
        state.document = doc
          ? {
              ...doc,
              pdfBytes: doc.pdfBytes.slice(),
            }
          : null;
        state.fields = [];
        state.selectedFieldId = null;
        state.placementMode = null;
        state.currentPageIndex = 0;
        state.past = [];
        state.future = [];
        state.isDirty = false;
        state.signatureModalFieldId = null;
      }),

    setZoom: (zoom) =>
      set((state) => {
        state.zoom = Math.min(300, Math.max(50, Math.round(zoom)));
      }),

    setCurrentPage: (pageIndex) =>
      set((state) => {
        if (!state.document) return;
        state.currentPageIndex = Math.min(
          Math.max(0, pageIndex),
          state.document.pageCount - 1,
        );
      }),

    setPlacementMode: (mode) =>
      set((state) => {
        state.placementMode = mode;
        if (mode) state.selectedFieldId = null;
      }),

    selectField: (id) =>
      set((state) => {
        state.selectedFieldId = id;
        if (id) state.placementMode = null;
      }),

    addField: (type, pageIndex, rect) => {
      let createdId = '';
      set((state) => {
        if (!state.document) return;
        const page = state.document.pages[pageIndex];
        if (!page) return;
        pushHistory(state);
        const defaults = DEFAULT_FIELD_SIZES[type];
        const sized: PdfRect = {
          x: rect.x,
          y: rect.y,
          width: rect.width > 4 ? rect.width : defaults.width,
          height: rect.height > 4 ? rect.height : defaults.height,
        };
        const clamped = clampPdfRect(sized, page.widthPt, page.heightPt);
        const field = createField(type, pageIndex, clamped);
        createdId = field.id;
        state.fields.push(field);
        state.selectedFieldId = field.id;
        state.placementMode = null;
        state.isDirty = true;
      });
      return createdId;
    },

    updateField: (id, patch) =>
      set((state) => {
        const idx = state.fields.findIndex((f) => f.id === id);
        if (idx < 0) return;
        pushHistory(state);
        const current = state.fields[idx];
        state.fields[idx] = { ...current, ...patch, id: current.id, type: current.type } as AnyField;
        state.isDirty = true;
      }),

    updateFieldRect: (id, rect) =>
      set((state) => {
        if (!state.document) return;
        const idx = state.fields.findIndex((f) => f.id === id);
        if (idx < 0) return;
        const field = state.fields[idx];
        const page = state.document.pages[field.pageIndex];
        if (!page) return;
        pushHistory(state);
        state.fields[idx].rect = clampPdfRect(rect, page.widthPt, page.heightPt);
        state.isDirty = true;
      }),

    deleteField: (id) =>
      set((state) => {
        const idx = state.fields.findIndex((f) => f.id === id);
        if (idx < 0) return;
        pushHistory(state);
        state.fields.splice(idx, 1);
        if (state.selectedFieldId === id) state.selectedFieldId = null;
        state.isDirty = true;
      }),

    deleteSelected: () => {
      const id = get().selectedFieldId;
      if (id) get().deleteField(id);
    },

    openSignatureModal: (fieldId) =>
      set((state) => {
        state.signatureModalFieldId = fieldId;
      }),

    closeSignatureModal: () =>
      set((state) => {
        state.signatureModalFieldId = null;
      }),

    applySignature: (fieldId, imageDataUrl) =>
      set((state) => {
        const idx = state.fields.findIndex((f) => f.id === fieldId);
        if (idx < 0) return;
        const field = state.fields[idx];
        if (field.type !== 'signature') return;
        pushHistory(state);
        (state.fields[idx] as SignatureField).imageDataUrl = imageDataUrl;
        state.signatureModalFieldId = null;
        state.isDirty = true;
      }),

    undo: () =>
      set((state) => {
        if (state.past.length === 0) return;
        state.future.unshift(cloneFields(state.fields));
        const prev = state.past.pop();
        if (prev) state.fields = prev;
        state.selectedFieldId = null;
        state.isDirty = true;
      }),

    redo: () =>
      set((state) => {
        if (state.future.length === 0) return;
        state.past.push(cloneFields(state.fields));
        const next = state.future.shift();
        if (next) state.fields = next;
        state.selectedFieldId = null;
        state.isDirty = true;
      }),

    canUndo: () => get().past.length > 0,
    canRedo: () => get().future.length > 0,

    reset: () =>
      set((state) => {
        state.document = null;
        state.fields = [];
        state.selectedFieldId = null;
        state.placementMode = null;
        state.zoom = 100;
        state.currentPageIndex = 0;
        state.past = [];
        state.future = [];
        state.signatureModalFieldId = null;
        state.isDirty = false;
      }),

    getFieldsForPage: (pageIndex) => get().fields.filter((f) => f.pageIndex === pageIndex),
  })),
);
