# PDF Field Editor

Production-ready static SPA for placing **text**, **date**, **signature**, and **comment** fields on PDFs, then exporting a fillable AcroForm PDF.

## Stack

- React 18 + TypeScript + Vite 5
- pdfjs-dist 4.x (render) + pdf-lib 1.17+ (export)
- react-rnd (drag / 8-handle resize)
- signature_pad 4.x
- Zustand 4 + Immer
- Tailwind CSS 3.4 + shadcn/ui
- Vitest + Testing Library + Playwright

## Quick start

```bash
cd pdf-field-editor
pnpm install
pnpm generate:sample-pdf   # writes public/sample.pdf
pnpm dev
```

Open the URL Vite prints (usually http://localhost:5173).

## Scripts

| Command | Purpose |
|---------|---------|
| `pnpm dev` | Local development |
| `pnpm build` | Production static build → `dist/` |
| `pnpm preview` | Serve `dist/` |
| `pnpm test` | Unit tests (Vitest) |
| `pnpm test:e2e` | Playwright e2e (builds + previews) |
| `pnpm generate:sample-pdf` | Create `public/sample.pdf` |

## Coordinate system

Field geometry is stored in **PDF user space** (origin bottom-left, Y up, points). The UI converts to screen space (top-left, Y down, CSS px × zoom) for rendering and `react-rnd`, then converts back on drag/resize.

## Keyboard shortcuts

| Key | Action |
|-----|--------|
| `T` / `D` / `S` / `C` | Placement mode: Text / Date / Signature / Comment |
| `Delete` / `Backspace` | Delete selected field |
| `Esc` | Clear selection / placement |
| `Ctrl+Z` | Undo |
| `Ctrl+Shift+Z` / `Ctrl+Y` | Redo |
| `+` / `-` | Zoom in / out (50–300%) |

## Deploy

### Vercel

```bash
cd pdf-field-editor
npx vercel --prod
```

Or connect the repo and set **Root Directory** to `pdf-field-editor`, build `pnpm build`, output `dist`.

### Netlify

```bash
cd pdf-field-editor
npx netlify deploy --prod --dir=dist
```

Or set base directory `pdf-field-editor`, build command `pnpm build`, publish `dist`.

## UAT

See [UAT.md](./UAT.md) for the acceptance checklist and evidence notes.
