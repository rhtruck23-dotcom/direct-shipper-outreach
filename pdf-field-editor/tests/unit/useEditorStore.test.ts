import { beforeEach, describe, expect, it } from 'vitest';
import { useEditorStore } from '@/store/useEditorStore';
import type { EditorDocument } from '@/types/fields';

function sampleDoc(): EditorDocument {
  return {
    fileName: 'test.pdf',
    pdfBytes: new Uint8Array([1, 2, 3]),
    pageCount: 2,
    pages: [
      { pageIndex: 0, widthPt: 612, heightPt: 792 },
      { pageIndex: 1, widthPt: 612, heightPt: 792 },
    ],
  };
}

describe('useEditorStore', () => {
  beforeEach(() => {
    useEditorStore.getState().reset();
  });

  it('supports CRUD for all field types', () => {
    const store = useEditorStore.getState();
    store.setDocument(sampleDoc());

    const textId = useEditorStore.getState().addField('text', 0, {
      x: 50,
      y: 700,
      width: 0,
      height: 0,
    });
    const dateId = useEditorStore.getState().addField('date', 0, {
      x: 50,
      y: 650,
      width: 100,
      height: 20,
    });
    const sigId = useEditorStore.getState().addField('signature', 1, {
      x: 50,
      y: 200,
      width: 180,
      height: 60,
    });
    const commentId = useEditorStore.getState().addField('comment', 0, {
      x: 300,
      y: 400,
      width: 120,
      height: 80,
    });

    let fields = useEditorStore.getState().fields;
    expect(fields).toHaveLength(4);
    expect(fields.map((f) => f.type).sort()).toEqual(['comment', 'date', 'signature', 'text']);

    useEditorStore.getState().updateField(textId, { name: 'ShipperName', defaultValue: 'Acme' } as never);
    useEditorStore.getState().updateFieldRect(dateId, { x: 60, y: 640, width: 110, height: 22 });
    useEditorStore.getState().applySignature(sigId, 'data:image/png;base64,abc');
    useEditorStore.getState().updateField(commentId, { text: 'Check this' } as never);

    fields = useEditorStore.getState().fields;
    expect(fields.find((f) => f.id === textId)?.name).toBe('ShipperName');
    expect(fields.find((f) => f.id === dateId)?.rect.x).toBe(60);
    const sig = fields.find((f) => f.id === sigId);
    expect(sig?.type).toBe('signature');
    if (sig?.type === 'signature') expect(sig.imageDataUrl).toContain('data:image/png');
    const comment = fields.find((f) => f.id === commentId);
    expect(comment?.type).toBe('comment');
    if (comment?.type === 'comment') expect(comment.text).toBe('Check this');

    useEditorStore.getState().deleteField(dateId);
    expect(useEditorStore.getState().fields).toHaveLength(3);
    expect(useEditorStore.getState().fields.find((f) => f.id === dateId)).toBeUndefined();
  });

  it('undo/redo restores field list', () => {
    useEditorStore.getState().setDocument(sampleDoc());
    useEditorStore.getState().addField('text', 0, { x: 10, y: 10, width: 50, height: 20 });
    expect(useEditorStore.getState().fields).toHaveLength(1);

    useEditorStore.getState().addField('date', 0, { x: 20, y: 20, width: 50, height: 20 });
    expect(useEditorStore.getState().fields).toHaveLength(2);

    useEditorStore.getState().undo();
    expect(useEditorStore.getState().fields).toHaveLength(1);

    useEditorStore.getState().undo();
    expect(useEditorStore.getState().fields).toHaveLength(0);

    useEditorStore.getState().redo();
    expect(useEditorStore.getState().fields).toHaveLength(1);

    useEditorStore.getState().redo();
    expect(useEditorStore.getState().fields).toHaveLength(2);
  });

  it('clamps zoom to 50–300', () => {
    useEditorStore.getState().setZoom(10);
    expect(useEditorStore.getState().zoom).toBe(50);
    useEditorStore.getState().setZoom(500);
    expect(useEditorStore.getState().zoom).toBe(300);
    useEditorStore.getState().setZoom(125);
    expect(useEditorStore.getState().zoom).toBe(125);
  });
});
