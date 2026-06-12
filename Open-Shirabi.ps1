$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Exe = Join-Path $Root "Shirabi.exe"
$EnvFile = Join-Path $Root ".env"
$Port = 7000
$Bind = "0.0.0.0"
$LauncherLog = Join-Path $Root "launcher_open.log"

function Read-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name
    )
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
            continue
        }
        $idx = $trimmed.IndexOf("=")
        if ($idx -le 0) {
            continue
        }
        $key = $trimmed.Substring(0, $idx).Trim()
        if ($key -ne $Name) {
            continue
        }
        return $trimmed.Substring($idx + 1).Trim().Trim('"').Trim("'")
    }
    return $null
}

$envPort = Read-DotEnvValue -Path $EnvFile -Name "APP_PORT"
if ($envPort -and ($envPort -as [int])) {
    $Port = [int]$envPort
}

$envBind = Read-DotEnvValue -Path $EnvFile -Name "APP_BIND"
if ($envBind) {
    $Bind = $envBind
}

$LocalUrl = "http://127.0.0.1:$Port/"

function Test-ShirabiHttp {
    param([string]$Url)
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Write-LaunchLog {
    param([string]$Message)
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -LiteralPath $LauncherLog -Value "[$stamp] $Message"
}

Write-LaunchLog "Open-Shirabi requested. bind=$Bind port=$Port url=$LocalUrl"

if (-not (Test-ShirabiHttp -Url $LocalUrl)) {
    if (-not (Test-Path -LiteralPath $Exe)) {
        Write-LaunchLog "Missing launcher: $Exe"
        throw "Shirabi.exe was not found at $Exe"
    }

    Write-LaunchLog "Backend not reachable yet; starting Shirabi.exe"
    Start-Process -FilePath $Exe -WorkingDirectory $Root | Out-Null

    $deadline = (Get-Date).AddSeconds(90)
    while ((Get-Date) -lt $deadline) {
        if (Test-ShirabiHttp -Url $LocalUrl) {
            break
        }
        Start-Sleep -Seconds 2
    }
}

if (-not (Test-ShirabiHttp -Url $LocalUrl)) {
    Write-LaunchLog "Timed out waiting for $LocalUrl"
    throw "Shirabi did not become reachable at $LocalUrl. Check launcher_error.txt or app logs."
}

Write-LaunchLog "Opening $LocalUrl"
Start-Process $LocalUrl
