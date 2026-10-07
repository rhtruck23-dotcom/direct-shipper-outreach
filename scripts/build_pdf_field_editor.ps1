# Build PDF Field Editor and sync into src/pdf_field_editor/frontend for Streamlit.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
Write-Host "Building pdf-field-editor -> dist + src/pdf_field_editor/frontend ..." -ForegroundColor Cyan
pnpm --dir pdf-field-editor build
if (-not (Test-Path "src\pdf_field_editor\frontend\index.html")) {
    throw "Build did not produce src/pdf_field_editor/frontend/index.html"
}
Write-Host "OK - Streamlit can embed the bundled SPA (no external URL needed)." -ForegroundColor Green
