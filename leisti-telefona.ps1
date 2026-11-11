$ErrorActionPreference = "Stop"

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    try {
        $process = Start-Process -FilePath "powershell.exe" -Verb RunAs -Wait -PassThru -ArgumentList $arguments
    } catch {
        Write-Host "Windows langas nepatvirtintas. Telefonas sio kompiuterio nepasieks."
        exit 1
    }
    exit $process.ExitCode
}

$rule = Get-NetFirewallRule -DisplayName "RRR forma" -ErrorAction SilentlyContinue
if (-not $rule) {
    New-NetFirewallRule -DisplayName "RRR forma" -Name "RRR forma" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Any -RemoteAddress LocalSubnet | Out-Null
}

Write-Host "Telefonui leista."
exit 0
