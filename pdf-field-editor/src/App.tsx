import { useEffect } from 'react';
import { Toolbar } from '@/components/Toolbar';
import { PdfViewer } from '@/components/PdfViewer';
import { PropertyPanel } from '@/components/PropertyPanel';
import { SignatureModal } from '@/components/SignatureModal';
import { Toaster } from '@/components/ui/toaster';
import { useEditorStore } from '@/store/useEditorStore';
import type { FieldType } from '@/types/fields';

export default function App() {
  const setPlacementMode = useEditorStore((s) => s.setPlacementMode);
  const deleteSelected = useEditorStore((s) => s.deleteSelected);
  const undo = useEditorStore((s) => s.undo);
  const redo = useEditorStore((s) => s.redo);
  const setZoom = useEditorStore((s) => s.setZoom);
  const zoom = useEditorStore((s) => s.zoom);
  const documentMeta = useEditorStore((s) => s.document);
  const selectedFieldId = useEditorStore((s) => s.selectedFieldId);
  const placementMode = useEditorStore((s) => s.placementMode);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const typing =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable);

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault();
        undo();
        return;
      }
      if (
        (e.ctrlKey || e.metaKey) &&
        (e.key.toLowerCase() === 'y' || (e.key.toLowerCase() === 'z' && e.shiftKey))
      ) {
        e.preventDefault();
        redo();
        return;
      }

      if (typing) return;

      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedFieldId) {
        e.preventDefault();
        deleteSelected();
        return;
      }

      if (e.key === 'Escape') {
        useEditorStore.getState().setPlacementMode(null);
        useEditorStore.getState().selectField(null);
        return;
      }

      if (!documentMeta) return;

      const map: Record<string, FieldType> = {
        t: 'text',
        d: 'date',
        s: 'signature',
        c: 'comment',
      };
      const lower = e.key.toLowerCase();
      if (map[lower] && !e.ctrlKey && !e.metaKey && !e.altKey) {
        e.preventDefault();
        const next = placementMode === map[lower] ? null : map[lower];
        setPlacementMode(next);
        return;
      }

      if (e.key === '+' || e.key === '=') {
        e.preventDefault();
        setZoom(zoom + 10);
      }
      if (e.key === '-' || e.key === '_') {
        e.preventDefault();
        setZoom(zoom - 10);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [
    deleteSelected,
    documentMeta,
    placementMode,
    redo,
    selectedFieldId,
    setPlacementMode,
    setZoom,
    undo,
    zoom,
  ]);

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-50 text-slate-900" data-testid="app-root">
      <Toolbar />
      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1">
          <PdfViewer />
        </main>
        <PropertyPanel />
      </div>
      <SignatureModal />
      <Toaster />
    </div>
  );
}
