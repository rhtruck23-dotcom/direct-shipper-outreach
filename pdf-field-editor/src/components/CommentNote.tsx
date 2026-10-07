import type { CommentField } from '@/types/fields';
import { format } from 'date-fns';
import { StickyNote } from 'lucide-react';

interface CommentNoteProps {
  field: CommentField;
  compact?: boolean;
}

export function CommentNote({ field, compact = false }: CommentNoteProps) {
  const when = field.createdAt
    ? format(new Date(field.createdAt), 'MMM d, yyyy HH:mm')
    : '';

  if (compact) {
    return (
      <div
        className="flex h-full w-full flex-col overflow-hidden rounded border border-amber-400 bg-amber-100/95 p-1 text-[10px] leading-tight text-amber-950 shadow-sm"
        data-testid={`comment-note-${field.id}`}
      >
        <div className="flex items-center gap-1 font-semibold">
          <StickyNote className="h-3 w-3 shrink-0" />
          <span className="truncate">{field.author || 'Note'}</span>
        </div>
        <p className="mt-0.5 line-clamp-3 whitespace-pre-wrap">{field.text || 'Empty comment'}</p>
      </div>
    );
  }

  return (
    <div
      className="rounded-md border border-amber-400 bg-amber-50 p-3 text-sm shadow"
      data-testid={`comment-note-${field.id}`}
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-medium text-amber-900">{field.author || 'Comment'}</span>
        <span className="text-xs text-amber-700">{when}</span>
      </div>
      <p className="whitespace-pre-wrap text-amber-950">{field.text || 'Empty comment'}</p>
    </div>
  );
}
