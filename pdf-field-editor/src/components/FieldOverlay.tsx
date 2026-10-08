import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type MouseEvent,
} from 'react';
import { Rnd } from 'react-rnd';
import type { AnyField, PageInfo, RedactionField, TextField, TypewriterField } from '@/types/fields';
import { FIELD_COLORS, redactionFillHex } from '@/types/fields';
import { pdfRectToScreen, screenRectToPdf } from '@/lib/coordinateUtils';
import { useEditorStore } from '@/store/useEditorStore';
import { CommentNote } from '@/components/CommentNote';
import { Calendar, EyeOff, PenLine, Type } from 'lucide-react';
import { cn } from '@/lib/utils';

interface FieldOverlayProps {
  field: AnyField;
  page: PageInfo;
  scale: number;
}

export function FieldOverlay({ field, page, scale }: FieldOverlayProps) {
  const selectedFieldId = useEditorStore((s) => s.selectedFieldId);
  const selectField = useEditorStore((s) => s.selectField);
  const updateField = useEditorStore((s) => s.updateField);
  const updateFieldRect = useEditorStore((s) => s.updateFieldRect);
  const openSignatureModal = useEditorStore((s) => s.openSignatureModal);
  const selected = selectedFieldId === field.id;
  const color = FIELD_COLORS[field.type];
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement | HTMLInputElement>(null);

  const screen = useMemo(
    () => pdfRectToScreen(field.rect, page.heightPt, scale),
    [field.rect, page.heightPt, scale],
  );

  const autoEditOnce = useRef(false);

  useEffect(() => {
    if (!selected) {
      setEditing(false);
      autoEditOnce.current = false;
    }
  }, [selected]);

  // Typewriter: click to place → type immediately
  useEffect(() => {
    if (
      selected &&
      field.type === 'typewriter' &&
      !(field as TypewriterField).text &&
      !autoEditOnce.current
    ) {
      autoEditOnce.current = true;
      setEditing(true);
    }
  }, [selected, field]);

  useEffect(() => {
    if (editing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select?.();
    }
  }, [editing]);

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

  const startInlineEdit = () => {
    if (field.type === 'text' || field.type === 'typewriter' || field.type === 'comment') {
      setEditing(true);
    }
  };

  const commitInline = (raw: string) => {
    if (field.type === 'text') {
      updateField(field.id, { defaultValue: raw } as Partial<TextField>);
    } else if (field.type === 'typewriter') {
      updateField(field.id, { text: raw } as Partial<TypewriterField>);
    } else if (field.type === 'comment') {
      updateField(field.id, { text: raw });
    }
    setEditing(false);
  };

  const editValue =
    field.type === 'text'
      ? field.defaultValue
      : field.type === 'typewriter' || field.type === 'comment'
        ? field.text
        : '';

  const label = (() => {
    if (editing && (field.type === 'text' || field.type === 'typewriter' || field.type === 'comment')) {
      const multiline = field.type !== 'text' || field.multiline;
      const common = {
        ref: inputRef as never,
        className:
          'h-full w-full resize-none border-0 bg-white/95 px-1 text-[11px] text-slate-900 outline-none',
        defaultValue: editValue,
        onClick: (e: MouseEvent) => e.stopPropagation(),
        onPointerDown: (e: MouseEvent) => e.stopPropagation(),
        onBlur: (e: { currentTarget: HTMLInputElement | HTMLTextAreaElement }) =>
          commitInline(e.currentTarget.value),
        onKeyDown: (e: KeyboardEvent) => {
          if (e.key === 'Escape') {
            e.preventDefault();
            setEditing(false);
          }
          if (e.key === 'Enter' && !e.shiftKey && field.type === 'text' && !field.multiline) {
            e.preventDefault();
            commitInline((e.target as HTMLInputElement).value);
          }
        },
        'data-testid': `field-inline-edit-${field.id}`,
      };
      return multiline ? (
        <textarea {...common} />
      ) : (
        <input type="text" {...common} />
      );
    }

    switch (field.type) {
      case 'text':
        return (
          <span className="flex items-center gap-1 truncate px-1 text-[10px] font-medium">
            <Type className="h-3 w-3 shrink-0" />
            {field.defaultValue || field.name}
          </span>
        );
      case 'typewriter':
        return (
          <span
            className="flex h-full w-full items-center truncate px-1 font-serif text-[11px]"
            style={{ color: field.color || '#111827', fontSize: field.fontSize || 12 }}
          >
            {field.text || 'Type here…'}
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
      case 'redaction': {
        const fill = redactionFillHex(field.color);
        const isLight = field.color === 'white';
        return (
          <span
            className={cn(
              'flex h-full w-full items-center justify-center gap-1 px-1 text-[10px] font-semibold tracking-wide',
              isLight ? 'text-slate-600' : 'text-white/90',
            )}
            style={{ background: fill }}
          >
            <EyeOff className="h-3 w-3 shrink-0 opacity-80" />
            {field.color === 'void' ? 'VOID' : 'REDACT'}
          </span>
        );
      }
    }
  })();

  return (
    <Rnd
      size={{ width: screen.width, height: screen.height }}
      position={{ x: screen.x, y: screen.y }}
      bounds="parent"
      enableResizing={
        selected
          ? {
              top: true,
              right: true,
              bottom: true,
              left: true,
              topRight: true,
              bottomRight: true,
              bottomLeft: true,
              topLeft: true,
            }
          : false
      }
      disableDragging={!selected || editing}
      onDragStart={() => selectField(field.id)}
      onDragStop={onDragStop}
      onResizeStop={onResizeStop}
      onClick={(e: MouseEvent) => {
        e.stopPropagation();
        selectField(field.id);
      }}
      onDoubleClick={(e: MouseEvent) => {
        e.stopPropagation();
        selectField(field.id);
        if (field.type === 'signature') {
          openSignatureModal(field.id);
        } else {
          startInlineEdit();
        }
      }}
      data-testid={`field-overlay-${field.id}`}
      data-field-type={field.type}
      className={cn(
        'group absolute z-10 flex items-center justify-center overflow-visible rounded-sm',
        selected && 'z-20 ring-2 ring-offset-1',
      )}
      style={{
        border: `1.5px solid ${
          field.type === 'redaction'
            ? field.color === 'white'
              ? '#94a3b8'
              : redactionFillHex((field as RedactionField).color)
            : color
        }`,
        background:
          field.type === 'comment'
            ? 'transparent'
            : field.type === 'redaction'
              ? 'transparent'
              : field.type === 'typewriter'
                ? `${color}18`
                : `${color}22`,
        boxShadow: selected ? `0 0 0 1px ${color}` : undefined,
      }}
      resizeHandleClasses={
        selected
          ? {
              topLeft: 'lt-rnd-handle',
              topRight: 'lt-rnd-handle',
              bottomLeft: 'lt-rnd-handle',
              bottomRight: 'lt-rnd-handle',
              top: 'lt-rnd-handle lt-rnd-handle-edge',
              right: 'lt-rnd-handle lt-rnd-handle-edge',
              bottom: 'lt-rnd-handle lt-rnd-handle-edge',
              left: 'lt-rnd-handle lt-rnd-handle-edge',
            }
          : undefined
      }
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
      <div
        className={cn(
          'flex h-full w-full items-center justify-center text-slate-800',
          editing ? 'pointer-events-auto' : 'pointer-events-none',
        )}
      >
        {label}
      </div>
    </Rnd>
  );
}

function handleStyle(color: string, edge = false): CSSProperties {
  return {
    width: edge ? 10 : 12,
    height: edge ? 10 : 12,
    background: '#fff',
    border: `2px solid ${color}`,
    borderRadius: 2,
    zIndex: 40,
    boxShadow: '0 0 0 1px rgba(15,23,42,0.15)',
  };
}
