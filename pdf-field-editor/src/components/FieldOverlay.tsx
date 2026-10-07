import { useCallback, useMemo, type CSSProperties, type MouseEvent } from 'react';
import { Rnd } from 'react-rnd';
import type { AnyField, PageInfo } from '@/types/fields';
import { FIELD_COLORS } from '@/types/fields';
import { pdfRectToScreen, screenRectToPdf } from '@/lib/coordinateUtils';
import { useEditorStore } from '@/store/useEditorStore';
import { CommentNote } from '@/components/CommentNote';
import { Calendar, PenLine, Type } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FieldOverlayProps {
  field: AnyField;
  page: PageInfo;
  scale: number;
}

export function FieldOverlay({ field, page, scale }: FieldOverlayProps) {
  const selectedFieldId = useEditorStore((s) => s.selectedFieldId);
  const selectField = useEditorStore((s) => s.selectField);
  const updateFieldRect = useEditorStore((s) => s.updateFieldRect);
  const openSignatureModal = useEditorStore((s) => s.openSignatureModal);
  const selected = selectedFieldId === field.id;
  const color = FIELD_COLORS[field.type];

  const screen = useMemo(
    () => pdfRectToScreen(field.rect, page.heightPt, scale),
    [field.rect, page.heightPt, scale],
  );

  const onDragStop = useCallback(
    (_e: unknown, d: { x: number; y: number }) => {
      const pdf = screenRectToPdf(
        { x: d.x, y: d.y, width: screen.width, height: screen.height },
        page.heightPt,
        scale,
      );
      updateFieldRect(field.id, pdf);
    },
    [field.id, page.heightPt, scale, screen.height, screen.width, updateFieldRect],
  );

  const onResizeStop = useCallback(
    (
      _e: unknown,
      _dir: unknown,
      ref: HTMLElement,
      _delta: unknown,
      position: { x: number; y: number },
    ) => {
      const pdf = screenRectToPdf(
        {
          x: position.x,
          y: position.y,
          width: ref.offsetWidth,
          height: ref.offsetHeight,
        },
        page.heightPt,
        scale,
      );
      updateFieldRect(field.id, pdf);
    },
    [field.id, page.heightPt, scale, updateFieldRect],
  );

  const label = (() => {
    switch (field.type) {
      case 'text':
        return (
          <span className="flex items-center gap-1 truncate px-1 text-[10px] font-medium">
            <Type className="h-3 w-3 shrink-0" />
            {field.defaultValue || field.name}
          </span>
        );
      case 'date':
        return (
          <span className="flex items-center gap-1 truncate px-1 text-[10px] font-medium">
            <Calendar className="h-3 w-3 shrink-0" />
            {field.defaultValue || field.name}
          </span>
        );
      case 'signature':
        return field.imageDataUrl ? (
          <img
            src={field.imageDataUrl}
            alt="Signature"
            className="h-full w-full object-contain p-0.5"
            draggable={false}
          />
        ) : (
          <span className="flex items-center gap-1 truncate px-1 text-[10px] font-medium">
            <PenLine className="h-3 w-3 shrink-0" />
            Sign here
          </span>
        );
      case 'comment':
        return <CommentNote field={field} compact />;
    }
  })();

  return (
    <Rnd
      size={{ width: screen.width, height: screen.height }}
      position={{ x: screen.x, y: screen.y }}
      bounds="parent"
      enableResizing={selected}
      disableDragging={!selected}
      onDragStart={() => selectField(field.id)}
      onDragStop={onDragStop}
      onResizeStop={onResizeStop}
      onClick={(e: MouseEvent) => {
        e.stopPropagation();
        selectField(field.id);
      }}
      onDoubleClick={(e: MouseEvent) => {
        e.stopPropagation();
        if (field.type === 'signature') {
          openSignatureModal(field.id);
        }
      }}
      data-testid={`field-overlay-${field.id}`}
      data-field-type={field.type}
      className={cn(
        'group absolute z-10 flex items-center justify-center overflow-hidden rounded-sm',
        selected && 'z-20 ring-2 ring-offset-1',
      )}
      style={{
        border: `1.5px solid ${color}`,
        background:
          field.type === 'comment'
            ? 'transparent'
            : `${color}22`,
        boxShadow: selected ? `0 0 0 1px ${color}` : undefined,
      }}
      resizeHandleStyles={
        selected
          ? {
              topLeft: handleStyle(color),
              topRight: handleStyle(color),
              bottomLeft: handleStyle(color),
              bottomRight: handleStyle(color),
              top: handleStyle(color, true),
              right: handleStyle(color, true),
              bottom: handleStyle(color, true),
              left: handleStyle(color, true),
            }
          : undefined
      }
    >
      <div className="pointer-events-none flex h-full w-full items-center justify-center text-slate-800">
        {label}
      </div>
    </Rnd>
  );
}

function handleStyle(color: string, edge = false): CSSProperties {
  return {
    width: edge ? 8 : 10,
    height: edge ? 8 : 10,
    background: '#fff',
    border: `2px solid ${color}`,
    borderRadius: 2,
  };
}
