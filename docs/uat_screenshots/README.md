# UAT screenshots

Drop failure screenshots here while testing `docs/E2E_UAT_CHECKLIST.md`.

## Naming

Use the test case ID plus `fail` (or a short note):

- `T-012-fail.png`
- `T-025-fail-task-tile.png`
- `T-120-fail-add-note.png`
- `T-122-fail-voice.png`

PNG or JPG is fine. One clear screenshot per Fail is enough; add a second only if needed to show the full problem.

## Coverage reminders (v2026.09.26f)

When filing fails, especially capture:

| Area | Example IDs |
|------|-------------|
| Clean Dashboard (ops only) | T-020, T-021, T-029 |
| Clickable tiles → lead/note | T-024, T-025, T-028, T-123 |
| Floating Add Note / voice | T-120, T-121, T-122 |
| Multi-Gmail pool (Org Setup) | T-023, T-082 |
| Agent / Autopilot | T-026, T-027, T-100 |
| Shipper / Carrier / Lead for X | T-030+, Carrier & Lead for X sections |

## Tip

Write the same filename in the **Screenshot** line of that test case in `docs/E2E_UAT_CHECKLIST.md`, then zip this folder (or share the PNGs) with your filled checklist when reporting fails.
