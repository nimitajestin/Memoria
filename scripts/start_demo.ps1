# Memoria demo launcher (Windows). Run from anywhere; uses the repo that contains this script.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

function Require-Command($Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Host "BLOCKED: '$Name' is not on PATH. Install it, then re-run this script."
        exit 1
    }
}

Require-Command ollama
Require-Command docker

Write-Host "Checking Ollama..."
try {
    $null = & ollama list 2>&1
    if ($LASTEXITCODE -ne 0) { throw "ollama list failed" }
} catch {
    Write-Host "BLOCKED: Ollama did not respond. Start the Ollama app/service, then re-run."
    Write-Host $_.Exception.Message
    exit 1
}

$listOut = & ollama list 2>&1 | Out-String
$missing = @()
if ($listOut -notmatch "phi3:mini") { $missing += "phi3:mini" }
if ($listOut -notmatch "nomic-embed-text") { $missing += "nomic-embed-text" }
if ($missing.Count -gt 0) {
    Write-Host "Required Ollama models are missing. Pull them, then re-run:"
    foreach ($model in $missing) {
        Write-Host "  ollama pull $model"
    }
    exit 1
}

if (-not $env:LLM_MODEL) { $env:LLM_MODEL = "phi3:mini" }
if (-not $env:EMBEDDING_MODEL) { $env:EMBEDDING_MODEL = "nomic-embed-text" }
Write-Host "Starting Docker Compose (build if needed). LLM_MODEL=$($env:LLM_MODEL) EMBEDDING_MODEL=$($env:EMBEDDING_MODEL)"
& docker compose up --build -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "BLOCKED: docker compose up failed. Install Docker Desktop, start it, then retry from the repo root."
    exit 1
}

function Test-LocalPort([int]$Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(500, $false)
        if (-not $ok) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

$deadline = (Get-Date).AddMinutes(3)
Write-Host "Waiting for MCP :8765 and Streamlit :8501..."
while ((Get-Date) -lt $deadline) {
    $mcp = Test-LocalPort 8765
    $ui = Test-LocalPort 8501
    if ($mcp -and $ui) {
        Write-Host "Memoria is running at http://localhost:8501"
        exit 0
    }
    Start-Sleep -Seconds 2
}

Write-Host "BLOCKED: compose started but ports 8765/8501 did not open within 3 minutes."
Write-Host "Manual check: docker compose ps ; docker compose logs"
exit 1
