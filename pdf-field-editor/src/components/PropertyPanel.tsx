import type { ReactNode } from 'react';
import { useEditorStore } from '@/store/useEditorStore';
import type {
  AnyField,
  CommentField,
  DateField,
  RedactionColor,
  RedactionField,
  SignatureField,
  TextField,
  TypewriterField,
} from '@/types/fields';
import { REDACTION_COLOR_OPTIONS } from '@/types/fields';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Trash2, PenLine } from 'lucide-react';
import { format } from 'date-fns';
import { cn } from '@/lib/utils';

export function PropertyPanel() {
  const fields = useEditorStore((s) => s.fields);
  const selectedFieldId = useEditorStore((s) => s.selectedFieldId);
  const updateField = useEditorStore((s) => s.updateField);
  const deleteField = useEditorStore((s) => s.deleteField);
  const openSignatureModal = useEditorStore((s) => s.openSignatureModal);

  const field = fields.find((f) => f.id === selectedFieldId) ?? null;

  if (!field) {
    return (
      <aside
        className="flex w-72 shrink-0 flex-col border-l border-slate-200 bg-white p-4 text-sm text-slate-500"
        data-testid="property-panel-empty"
      >
        <h2 className="mb-2 text-sm font-semibold text-slate-800">Properties</h2>
        <p>Select a field to edit its properties.</p>
      </aside>
    );
  }

  return (
    <aside
      className="flex w-72 shrink-0 flex-col gap-3 overflow-y-auto border-l border-slate-200 bg-white p-4"
      data-testid="property-panel"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-800">Properties</h2>
        <Button
          type="button"
          size="icon"
          variant="ghost"
          className="text-destructive"
          data-testid="delete-field"
          onClick={() => deleteField(field.id)}
          title="Delete field (Del)"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      <FieldRow label="Type">
        <span className="capitalize">{field.type}</span>
      </FieldRow>

      <FieldRow label="Name">
        <Input
          data-testid="prop-name"
          value={field.name}
          onChange={(e) => updateField(field.id, { name: e.target.value } as Partial<AnyField>)}
        />
      </FieldRow>

      <FieldRow label="Required">
        <input
          type="checkbox"
          data-testid="prop-required"
          checked={field.required}
          onChange={(e) => updateField(field.id, { required: e.target.checked } as Partial<AnyField>)}
          className="h-4 w-4"
        />
      </FieldRow>

      <FieldRow label="Page">{field.pageIndex + 1}</FieldRow>

      <div className="grid grid-cols-2 gap-2 text-xs text-slate-600">
        <div>X: {field.rect.x.toFixed(1)}</div>
        <div>Y: {field.rect.y.toFixed(1)}</div>
        <div>W: {field.rect.width.toFixed(1)}</div>
        <div>H: {field.rect.height.toFixed(1)}</div>
      </div>

      {field.type === 'text' && (
        <>
          <FieldRow label="Default value">
            <Input
              data-testid="prop-default-value"
              value={(field as TextField).defaultValue}
              onChange={(e) =>
                updateField(field.id, { defaultValue: e.target.value } as Partial<TextField>)
              }
            />
          </FieldRow>
          <FieldRow label="Font size">
            <Input
              type="number"
              min={6}
              max={72}
              value={(field as TextField).fontSize}
              onChange={(e) =>
                updateField(field.id, {
                  fontSize: Number(e.target.value) || 11,
                } as Partial<TextField>)
              }
            />
          </FieldRow>
          <FieldRow label="Multiline">
            <input
              type="checkbox"
              checked={(field as TextField).multiline}
              onChange={(e) =>
                updateField(field.id, { multiline: e.target.checked } as Partial<TextField>)
              }
              className="h-4 w-4"
            />
          </FieldRow>
        </>
      )}

      {field.type === 'date' && (
        <>
          <FieldRow label="Default date">
            <Input
              type="date"
              data-testid="prop-default-date"
              value={(field as DateField).defaultValue}
              onChange={(e) =>
                updateField(field.id, { defaultValue: e.target.value } as Partial<DateField>)
              }
            />
          </FieldRow>
          <FieldRow label="Format">
            <Input
              value={(field as DateField).format}
              onChange={(e) =>
                updateField(field.id, { format: e.target.value } as Partial<DateField>)
              }
            />
          </FieldRow>
        </>
      )}

      {field.type === 'signature' && (
        <div className="space-y-2">
          {(field as SignatureField).imageDataUrl ? (
            <img
              src={(field as SignatureField).imageDataUrl}
              alt="Current signature"
              className="max-h-24 w-full rounded border object-contain bg-white"
            />
          ) : (
            <p className="text-xs text-slate-500">No signature drawn yet.</p>
          )}
          <Button
            type="button"
            className="w-full"
            data-testid="open-signature-modal"
            onClick={() => openSignatureModal(field.id)}
          >
            <PenLine className="h-4 w-4" />
            Draw signature
          </Button>
        </div>
      )}

      {field.type === 'comment' && (
        <>
          <FieldRow label="Author">
            <Input
              data-testid="prop-author"
              value={(field as CommentField).author}
              onChange={(e) =>
                updateField(field.id, { author: e.target.value } as Partial<CommentField>)
              }
            />
          </FieldRow>
          <FieldRow label="Comment">
            <textarea
              data-testid="prop-comment-text"
              className="min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
              value={(field as CommentField).text}
              onChange={(e) =>
                updateField(field.id, { text: e.target.value } as Partial<CommentField>)
              }
            />
          </FieldRow>
          <p className="text-xs text-slate-500">
            Created{' '}
            {format(new Date((field as CommentField).createdAt), 'MMM d, yyyy HH:mm')}
          </p>
        </>
      )}

      {field.type === 'typewriter' && (
        <>
          <FieldRow label="Typewriter text">
            <textarea
              data-testid="prop-typewriter-text"
              className="min-h-[80px] w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
              value={(field as TypewriterField).text}
              onChange={(e) =>
                updateField(field.id, { text: e.target.value } as Partial<TypewriterField>)
              }
              placeholder="Click page → type; burns into PDF on Save/Download"
            />
          </FieldRow>
          <FieldRow label="Font size">
            <Input
              type="number"
              min={6}
              max={72}
              data-testid="prop-typewriter-size"
              value={(field as TypewriterField).fontSize}
              onChange={(e) =>
                updateField(field.id, {
                  fontSize: Number(e.target.value) || 12,
                } as Partial<TypewriterField>)
              }
            />
          </FieldRow>
          <FieldRow label="Color">
            <Input
              type="color"
              data-testid="prop-typewriter-color"
              value={(field as TypewriterField).color || '#111827'}
              onChange={(e) =>
                updateField(field.id, { color: e.target.value } as Partial<TypewriterField>)
              }
            />
          </FieldRow>
          <p className="text-xs text-slate-500">
            Stamped onto the page on export (not a fillable form field). Full rewrite of
            existing PDF paragraph text is not supported — use typewriter stamps instead.
          </p>
        </>
      )}

      {field.type === 'redaction' && (
        <>
          <FieldRow label="Cover color">
            <div className="grid grid-cols-2 gap-2" data-testid="prop-redaction-color">
              {REDACTION_COLOR_OPTIONS.map((opt) => {
                const active = (field as RedactionField).color === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    data-testid={`prop-redaction-${opt.value}`}
                    className={cn(
                      'flex items-center gap-2 rounded-md border px-2 py-1.5 text-left text-xs font-medium transition-colors',
                      active
                        ? 'border-slate-900 bg-slate-50 ring-1 ring-slate-900'
                        : 'border-slate-200 hover:border-slate-300',
                    )}
                    onClick={() =>
                      updateField(field.id, {
                        color: opt.value as RedactionColor,
                      } as Partial<RedactionField>)
                    }
                  >
                    <span
                      className="h-4 w-4 shrink-0 rounded-sm border border-slate-300"
                      style={{
                        background:
                          opt.value === 'void'
                            ? 'repeating-linear-gradient(45deg,#6b7280,#6b7280 2px,#9ca3af 2px,#9ca3af 4px)'
                            : opt.fill,
                      }}
                    />
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </FieldRow>
          <p className="text-xs text-slate-500">
            Solid cover burned into the PDF on Save/Download (not a form field). No outline or
            label is written to the exported PDF.
          </p>
        </>
      )}
    </aside>
  );
}

function FieldRow({ label, children }: { label: string; children?: ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-slate-600">
      {label}
      {children}
    </label>
  );
}
