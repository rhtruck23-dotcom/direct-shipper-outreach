import { useRef, type ReactNode } from 'react';
import {
  Calendar,
  Download,
  EyeOff,
  FileUp,
  Keyboard,
  Minus,
  PenLine,
  Plus,
  Redo2,
  Save,
  StickyNote,
  Type,
  Undo2,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useEditorStore } from '@/store/useEditorStore';
import { loadPdfFromFile } from '@/lib/pdfLoader';
import { downloadBytes, exportFillablePdf } from '@/lib/exportFillablePdf';
import { buildSaveToOutreachPayload, postSaveToOutreach } from '@/lib/outreachBridge';
import { toast } from '@/hooks/use-toast';
import type { FieldType } from '@/types/fields';
import { cn } from '@/lib/utils';

export function Toolbar() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const documentMeta = useEditorStore((s) => s.document);
  const placementMode = useEditorStore((s) => s.placementMode);
  const zoom = useEditorStore((s) => s.zoom);
  const setDocument = useEditorStore((s) => s.setDocument);
  const setPlacementMode = useEditorStore((s) => s.setPlacementMode);
  const setZoom = useEditorStore((s) => s.setZoom);
  const undo = useEditorStore((s) => s.undo);
  const redo = useEditorStore((s) => s.redo);
  const past = useEditorStore((s) => s.past);
  const future = useEditorStore((s) => s.future);
  const fields = useEditorStore((s) => s.fields);
  const currentPageIndex = useEditorStore((s) => s.currentPageIndex);
  const setCurrentPage = useEditorStore((s) => s.setCurrentPage);

  const onUpload = async (file: File | undefined) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.pdf')) {
      toast({ title: 'Invalid file', description: 'Please upload a PDF.', variant: 'destructive' });
      return;
    }
    try {
      const loaded = await loadPdfFromFile(file);
      setDocument(loaded.document);
      toast({
        title: 'PDF loaded',
        description: `${loaded.document.fileName} · ${loaded.document.pageCount} page(s)`,
      });
    } catch (err) {
      toast({
        title: 'Failed to load PDF',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const onExport = async () => {
    if (!documentMeta) return;
    try {
      const result = await exportFillablePdf({
        pdfBytes: documentMeta.pdfBytes,
        fields,
        fileName: documentMeta.fileName,
      });
      await downloadBytes(result.bytes, result.fileName);
      toast({
        title: 'Downloaded',
        description: `${result.fileName} (${result.formFieldCount} form fields)`,
      });
    } catch (err) {
      toast({
        title: 'Export failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const onSaveToOutreach = async () => {
    if (!documentMeta) return;
    if (fields.length === 0) {
      toast({
        title: 'Nothing to save',
        description: 'Place at least one field (or typewriter stamp) first.',
        variant: 'destructive',
      });
      return;
    }
    try {
      const payload = await buildSaveToOutreachPayload({
        document: documentMeta,
        fields,
      });
      const posted = postSaveToOutreach(payload);
      if (posted) {
        toast({
          title: 'Saved to Outreach',
          description: `«${payload.title}» · ${payload.fields.length} fillable field(s) sent to CRM.`,
        });
      } else {
        // Standalone / Vite: still download so work is not lost
        const bytes = Uint8Array.from(atob(payload.pdfBase64), (c) => c.charCodeAt(0));
        await downloadBytes(bytes, `${payload.title}-outreach.pdf`);
        toast({
          title: 'Downloaded (standalone)',
          description: 'Open inside LogixTrek Esign Docs to Save to Outreach CRM.',
        });
      }
    } catch (err) {
      toast({
        title: 'Save failed',
        description: err instanceof Error ? err.message : 'Unknown error',
        variant: 'destructive',
      });
    }
  };

  const toolBtn = (
    type: FieldType,
    label: string,
    shortcut: string,
    icon: ReactNode,
  ) => (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant={placementMode === type ? 'default' : 'outline'}
          data-testid={`tool-${type}`}
          aria-pressed={placementMode === type}
          className={cn(placementMode === type && 'ring-2 ring-offset-1')}
          disabled={!documentMeta}
          onClick={() => setPlacementMode(placementMode === type ? null : type)}
        >
          {icon}
          <span className="hidden lg:inline">{label}</span>
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        {label} ({shortcut})
      </TooltipContent>
    </Tooltip>
  );

  return (
    <TooltipProvider delayDuration={200}>
      <header
        className="flex flex-wrap items-center gap-2 border-b border-slate-200 bg-white px-3 py-2"
        data-testid="toolbar"
      >
        <div className="mr-2 text-sm font-bold tracking-tight text-slate-900">
          PDF Field Editor
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="application/pdf,.pdf"
          className="hidden"
          data-testid="file-input"
          onChange={(e) => {
            void onUpload(e.target.files?.[0]);
            e.target.value = '';
          }}
        />

        <Button
          type="button"
          size="sm"
          variant="secondary"
          data-testid="upload-button"
          onClick={() => fileInputRef.current?.click()}
        >
          <FileUp className="h-4 w-4" />
          Upload PDF
        </Button>

        <div className="mx-1 h-6 w-px bg-slate-200" />

        {toolBtn('text', 'Text', 'T', <Type className="h-4 w-4" />)}
        {toolBtn('date', 'Date', 'D', <Calendar className="h-4 w-4" />)}
        {toolBtn('signature', 'Signature', 'S', <PenLine className="h-4 w-4" />)}
        {toolBtn('typewriter', 'Typewriter', 'W', <Keyboard className="h-4 w-4" />)}
        {toolBtn('comment', 'Comment', 'C', <StickyNote className="h-4 w-4" />)}
        {toolBtn('redaction', 'Redact', 'R', <EyeOff className="h-4 w-4" />)}

        <div className="mx-1 h-6 w-px bg-slate-200" />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              data-testid="undo-button"
              disabled={past.length === 0}
              onClick={() => undo()}
            >
              <Undo2 className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Undo (Ctrl+Z)</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              data-testid="redo-button"
              disabled={future.length === 0}
              onClick={() => redo()}
            >
              <Redo2 className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Redo (Ctrl+Shift+Z)</TooltipContent>
        </Tooltip>

        <div className="mx-1 h-6 w-px bg-slate-200" />

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              data-testid="zoom-out"
              disabled={!documentMeta || zoom <= 50}
              onClick={() => setZoom(zoom - 10)}
            >
              <ZoomOut className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom out</TooltipContent>
        </Tooltip>

        <span className="min-w-[3.5rem] text-center text-xs tabular-nums text-slate-600" data-testid="zoom-label">
          {zoom}%
        </span>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              data-testid="zoom-in"
              disabled={!documentMeta || zoom >= 300}
              onClick={() => setZoom(zoom + 10)}
            >
              <ZoomIn className="h-4 w-4" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>Zoom in</TooltipContent>
        </Tooltip>

        {documentMeta && documentMeta.pageCount > 1 && (
          <>
            <div className="mx-1 h-6 w-px bg-slate-200" />
            <Button
              type="button"
              size="icon"
              variant="ghost"
              data-testid="prev-page"
              disabled={currentPageIndex <= 0}
              onClick={() => setCurrentPage(currentPageIndex - 1)}
            >
              <Minus className="h-4 w-4" />
            </Button>
            <span className="text-xs text-slate-600" data-testid="page-label">
              Page {currentPageIndex + 1} / {documentMeta.pageCount}
            </span>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              data-testid="next-page"
              disabled={currentPageIndex >= documentMeta.pageCount - 1}
              onClick={() => setCurrentPage(currentPageIndex + 1)}
            >
              <Plus className="h-4 w-4" />
            </Button>
          </>
        )}

        <div className="ml-auto flex items-center gap-2">
          {documentMeta && (
            <span className="hidden text-xs text-slate-500 sm:inline" data-testid="doc-name">
              {documentMeta.fileName} · {fields.length} field(s)
            </span>
          )}
          <Button
            type="button"
            size="sm"
            variant="default"
            data-testid="save-outreach-button"
            disabled={!documentMeta || fields.length === 0}
            onClick={() => void onSaveToOutreach()}
          >
            <Save className="h-4 w-4" />
            Save to Outreach
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            data-testid="download-button"
            disabled={!documentMeta}
            onClick={() => void onExport()}
          >
            <Download className="h-4 w-4" />
            Download
          </Button>
        </div>
      </header>
    </TooltipProvider>
  );
}
