$ErrorActionPreference = "Stop"

Set-Location -LiteralPath $PSScriptRoot

$env:PIP_NO_INDEX = $null
$env:HTTP_PROXY = $null
$env:HTTPS_PROXY = $null
$env:ALL_PROXY = $null

Write-Host "Starting Idiom Tool backend from: $PSScriptRoot"
Write-Host "Expected health response includes: version = 1.5.0-ollama-idiom-lookup"
Write-Host "Default fallback: free Ollama idiom lookup + web evidence when available. Literal guesses are suppressed."
Write-Host ""

.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
