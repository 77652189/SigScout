param([switch]$ConfigureFirewallOnly)

$ErrorActionPreference = "Stop"

$launcher = Join-Path $PSScriptRoot "start_SigScout_lan.ps1"

if ($ConfigureFirewallOnly) {
    & $launcher -ConfigureFirewallOnly
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Recovering SigScout LAN service..." -ForegroundColor Green
Write-Host "This will reapply the Windows firewall rule and restart SigScout on 0.0.0.0." -ForegroundColor Yellow
Write-Host ""

& $launcher -ForceRestart
exit $LASTEXITCODE
