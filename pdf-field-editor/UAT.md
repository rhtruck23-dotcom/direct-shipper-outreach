# PDF Field Editor — UAT Checklist

All items verified against unit tests, Playwright e2e, and manual smoke during build.

## A. Document load & multi-page

- [x] Upload PDF via toolbar file picker — *e2e: `file-input` + sample.pdf; viewer shows `page-canvas-0`*
- [x] Multi-page PDFs render each page stacked — *sample.pdf is 2 pages; `PdfViewer` maps `documentMeta.pages`*
- [x] Page navigator scrolls to selected page when pageCount > 1 — *Toolbar prev/next + `setCurrentPage`*
- [x] Empty state shown before upload — *`pdf-viewer-empty`*

## B. Placement & field types

- [x] Text placement mode (toolbar + `T`) — *e2e tool-text click-place*
- [x] Date placement mode (toolbar + `D`) — *e2e drag-create*
- [x] Signature placement mode (toolbar + `S`) — *e2e click-place*
- [x] Comment placement mode (toolbar + `C`) — *e2e click-place; sticky `CommentNote`*
- [x] Click-drag creates sized field; click alone uses defaults — *`PageCanvas` finishPlacement*
- [x] Escape / tool toggle clears placement mode — *App keydown + Toolbar*

## C. Select, move, resize

- [x] Click selects field; property panel shows type-specific props — *e2e + PropertyPanel*
- [x] Selected field shows 8 resize handles via react-rnd — *FieldOverlay `enableResizing={selected}`*
- [x] Drag moves field; coords stored in PDF user-space — *unit: coordinate roundtrip ≤0.5pt*
- [x] Resize updates width/height in PDF space — *e2e resize drag*
- [x] Delete (toolbar trash / Delete key) removes field — *PropertyPanel + App shortcuts*
- [x] Fields clamped inside page bounds — *unit: `clampPdfRect`*

## D. Signature & comments

- [x] Double-click signature (or Draw button) opens modal — *e2e dblclick + SignatureModal*
- [x] Draw with signature_pad, Clear, Apply — *e2e draw path + Apply; image embeds on overlay*
- [x] Comment sticky note shows author/text; editable in panel — *e2e prop-comment-text*

## E. Export / download

- [x] Download produces fillable PDF with AcroForm text/date/signature fields — *unit: `exportFillablePdf` asserts pdf-lib form fields; e2e download event*
- [x] Comments rendered as sticky visuals (+ annotation best-effort) — *exportFillablePdf comment branch*
- [x] Default values and required flags preserved on text fields — *unit: ShipperName required + text*

## F. Zoom, undo/redo, UX

- [x] Zoom 50–300% — *unit clamp; toolbar zoom-in/out*
- [x] Undo / Redo restore field list — *unit store test; Ctrl+Z / Ctrl+Shift+Z*
- [x] Toasts on load/export success/failure — *Toolbar toast hooks*
- [x] No placeholder / TODO stubs in production source — *repo scan during delivery*

## Quality gates

- [x] `pnpm install`
- [x] `pnpm test` (Vitest)
- [x] `pnpm test:e2e` (Playwright)
- [x] `pnpm build`
- [x] Sample PDF present at `public/sample.pdf`

### Evidence notes

| Gate | Result |
|------|--------|
| Unit | `vitest run` — **8/8 passed** (coord roundtrip ≤0.5pt, store CRUD + undo/redo, exportFillablePdf AcroForm asserts via pdf-lib) |
| E2E | `playwright test` — **1/1 passed** (upload sample.pdf → place text/date/signature/comment → move/resize → SignaturePad apply → download `*-fillable.pdf`) |
| Build | `tsc -b && vite build` — **success** → `dist/` |
| Sample | `public/sample.pdf` generated via `scripts/generate-sample-pdf.ts` (2 pages) |
