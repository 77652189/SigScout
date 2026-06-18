param(
    [switch]$ConfigureFirewallOnly,
    [switch]$ForceRestart
)

$ErrorActionPreference = "Stop"

$projectName = "SigScout"
$port = 8506
$ruleName = "SigScout Streamlit 8506 LAN"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$appPath = "src/sigscout/ui/streamlit_app.py"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-FirewallRuleReady {
    $rule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $rule -or $rule.Enabled -ne "True" -or $rule.Direction -ne "Inbound" -or $rule.Action -ne "Allow") {
        return $false
    }

    $portFilter = $rule | Get-NetFirewallPortFilter
    $addressFilter = $rule | Get-NetFirewallAddressFilter
    return ($portFilter.Protocol -eq "TCP" -and $portFilter.LocalPort -eq "$port" -and $addressFilter.RemoteAddress -eq "LocalSubnet")
}

function Ensure-FirewallRule {
    if (-not (Test-IsAdministrator)) {
        Write-Host "Administrator permission is required to configure the Windows firewall rule. Requesting UAC..." -ForegroundColor Yellow
        $args = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"", "-ConfigureFirewallOnly")
        Start-Process -FilePath "powershell.exe" -ArgumentList $args -Verb RunAs -Wait
        return
    }

    $rules = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if (-not $rules) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port -RemoteAddress LocalSubnet -Profile Any -Enabled True | Out-Null
    } else {
        $rules | Set-NetFirewallRule -Enabled True -Direction Inbound -Action Allow -Profile Any
        $rules | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $port
        $rules | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter -RemoteAddress LocalSubnet
    }
}

function Test-ListeningOnLan {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $address = [string]$connection.LocalAddress
        if ($address -eq "0.0.0.0" -or $address -eq "::" -or ($address -notlike "127.*" -and $address -ne "::1")) {
            return $true
        }
    }
    return $false
}

function Get-PortOwner {
    $connection = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $connection) {
        return $null
    }
    return Get-CimInstance Win32_Process -Filter "ProcessId=$($connection.OwningProcess)" -ErrorAction SilentlyContinue
}

function Stop-PortOwner {
    $connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($processId in $processIds) {
        if (-not $processId) {
            continue
        }
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
        $commandLine = [string]$process.CommandLine
        $isThisApp = ($commandLine -like "*src/sigscout/ui/streamlit_app.py*" -or $commandLine -like "*src\sigscout\ui\streamlit_app.py*")
        if ($isThisApp) {
            Write-Host "Stopping old SigScout process on port $port (PID $processId)..." -ForegroundColor Yellow
            Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        }
    }
}

function Test-HealthOk {
    try {
        $response = Invoke-WebRequest -Uri "http://127.0.0.1:$port/_stcore/health" -UseBasicParsing -TimeoutSec 5
        return ($response.Content.Trim() -eq "ok")
    } catch {
        return $false
    }
}

function Write-LanUrls {
    $lanAddresses = Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.InterfaceAlias -notlike "*WSL*" } |
        Select-Object -ExpandProperty IPAddress

    foreach ($address in $lanAddresses) {
        Write-Host "  http://$address`:$port" -ForegroundColor Green
    }
}

if ($ConfigureFirewallOnly) {
    Ensure-FirewallRule
    exit
}

if (-not (Test-FirewallRuleReady)) {
    Ensure-FirewallRule
}

Set-Location $projectRoot

$owner = Get-PortOwner
if ($owner) {
    $commandLine = [string]$owner.CommandLine
    $isThisApp = ($commandLine -like "*src/sigscout/ui/streamlit_app.py*" -or $commandLine -like "*src\sigscout\ui\streamlit_app.py*")
    if ($ForceRestart -and $isThisApp) {
        Stop-PortOwner
        Start-Sleep -Seconds 2
        $owner = Get-PortOwner
    } elseif ($isThisApp -and (Test-HealthOk) -and (Test-ListeningOnLan)) {
        Write-Host ""
        Write-Host "$projectName is already running. No need to start it again." -ForegroundColor Green
        Write-Host "LAN URLs:" -ForegroundColor Green
        Write-LanUrls
        Write-Host ""
        Write-Host "Local URL: http://127.0.0.1:$port" -ForegroundColor Green
        Write-Host ""
        exit 0
    } elseif ($isThisApp -and (Test-HealthOk) -and -not (Test-ListeningOnLan)) {
        Write-Host ""
        Write-Host "$projectName is running on localhost only. Restarting it for LAN access..." -ForegroundColor Yellow
        Stop-PortOwner
        Start-Sleep -Seconds 2
        $owner = Get-PortOwner
    }

    if ($owner) {
        Write-Host ""
        Write-Host "Port $port is already in use. Cannot start $projectName." -ForegroundColor Red
        Write-Host "Owner PID: $($owner.ProcessId)" -ForegroundColor Yellow
        Write-Host "Owner command: $([string]$owner.CommandLine)" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "If this is an old project service, close that window or run recover_SigScout_lan.bat." -ForegroundColor Yellow
        exit 1
    }
}

$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

Write-Host ""
Write-Host "$projectName will start on the LAN:" -ForegroundColor Green
Write-LanUrls
Write-Host ""
Write-Host "To stop the service, close this window or press Ctrl+C." -ForegroundColor Yellow
Write-Host ""

& $python -m streamlit run $appPath --server.address=0.0.0.0 --server.port=$port
