import { useCallback, useRef } from 'react';
import SignaturePad from 'signature_pad';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useEditorStore } from '@/store/useEditorStore';

type CanvasWithPad = HTMLCanvasElement & { __signaturePad?: SignaturePad };

export function SignatureModal() {
  const fieldId = useEditorStore((s) => s.signatureModalFieldId);
  const closeSignatureModal = useEditorStore((s) => s.closeSignatureModal);
  const applySignature = useEditorStore((s) => s.applySignature);
  const fields = useEditorStore((s) => s.fields);
  const padRef = useRef<SignaturePad | null>(null);
  const existingImage = useRef<string>('');

  const field = fields.find((f) => f.id === fieldId && f.type === 'signature');
  const open = Boolean(fieldId && field);
  existingImage.current =
    field && field.type === 'signature' ? field.imageDataUrl : '';

  const canvasRef = useCallback((canvas: HTMLCanvasElement | null) => {
    if (padRef.current) {
      padRef.current.off();
      padRef.current = null;
    }
    if (!canvas) return;

    const ratio = Math.max(window.devicePixelRatio || 1, 1);
    canvas.width = 500 * ratio;
    canvas.height = 200 * ratio;
    canvas.style.width = '500px';
    canvas.style.height = '200px';
    const ctx = canvas.getContext('2d');
    if (ctx) ctx.scale(ratio, ratio);

    const pad = new SignaturePad(canvas, {
      backgroundColor: 'rgb(255,255,255)',
      penColor: 'rgb(16, 24, 40)',
    });
    padRef.current = pad;
    (canvas as CanvasWithPad).__signaturePad = pad;
    canvas.dataset.padReady = 'true';

    if (existingImage.current) {
      pad.fromDataURL(existingImage.current);
    }
  }, []);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) closeSignatureModal();
      }}
    >
      <DialogContent className="sm:max-w-[560px]" data-testid="signature-modal">
        <DialogHeader>
          <DialogTitle>Draw signature</DialogTitle>
          <DialogDescription>
            Sign in the box below, then apply to the selected signature field.
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-md border border-slate-300 bg-white">
          <canvas
            ref={canvasRef}
            className="w-full touch-none"
            data-testid="signature-canvas"
          />
        </div>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            type="button"
            variant="outline"
            onClick={() => padRef.current?.clear()}
            data-testid="signature-clear"
          >
            Clear
          </Button>
          <Button type="button" variant="ghost" onClick={closeSignatureModal}>
            Cancel
          </Button>
          <Button
            type="button"
            data-testid="signature-apply"
            onClick={() => {
              if (!fieldId || !padRef.current) return;
              if (padRef.current.isEmpty()) return;
              applySignature(fieldId, padRef.current.toDataURL('image/png'));
            }}
          >
            Apply signature
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
