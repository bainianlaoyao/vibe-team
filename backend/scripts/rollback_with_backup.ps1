param(
    [string]$DatabasePath = ".\beebeebrain.db",
    [string]$DowngradeTarget = "-1",
    [switch]$SkipDowngrade
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $DatabasePath)) {
    Write-Error "Database file not found: $DatabasePath"
    exit 1
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = "$DatabasePath.$timestamp.bak"

Copy-Item -Path $DatabasePath -Destination $backupPath -Force
Write-Host "Database backup created: $backupPath"

if (-not $SkipDowngrade) {
    Write-Host "Running alembic downgrade target: $DowngradeTarget"
    uv run alembic downgrade $DowngradeTarget
}

Write-Host "Rollback flow finished."
