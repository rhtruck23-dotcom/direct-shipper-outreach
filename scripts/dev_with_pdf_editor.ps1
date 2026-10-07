# Start Streamlit (8501) + PDF Field Editor Vite (5173) for local Esign embed.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\dev_with_pdf_editor.ps1
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "LogixTrek - Streamlit + PDF Field Editor" -ForegroundColor Cyan
Write-Host "  Streamlit:  http://127.0.0.1:8501  -> Settings -> Esign Docs" -ForegroundColor Green
Write-Host "  PDF editor: http://127.0.0.1:5173  (also embedded in Compose)" -ForegroundColor Green
Write-Host ""

$env:PDF_FIELD_EDITOR_URL = "http://127.0.0.1:5173"

$vite = Start-Process -PassThru -WindowStyle Normal -FilePath "pnpm" -ArgumentList @(
    "--dir",
    "pdf-field-editor",
    "dev",
    "--host",
    "127.0.0.1",
    "--port",
    "5173"
) -WorkingDirectory $Root

Start-Sleep -Seconds 2

try {
    python -m streamlit run app.py --server.port 8501
} finally {
    if ($vite -and -not $vite.HasExited) {
        Stop-Process -Id $vite.Id -Force -ErrorAction SilentlyContinue
    }
}
