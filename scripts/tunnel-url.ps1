# Prints the live Cloudflare Quick Tunnel URL from the tunnel container's logs.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tunnel-url.ps1 [-Docker "wsl docker"] [-WaitSeconds 60]
#
# Takes the LAST URL in the logs: every tunnel restart mints a new random host,
# and the earlier ones are dead. Ignores api.trycloudflare.com, which only
# appears in cloudflared's own error lines.
param(
    [string]$Docker = "docker",
    [int]$WaitSeconds = 0
)

function Get-TunnelUrl {
    $parts = $Docker -split ' '
    $exe = $parts[0]
    $rest = @()
    if ($parts.Length -gt 1) { $rest = $parts[1..($parts.Length - 1)] }
    $logs = & $exe @rest compose logs --no-color tunnel 2>&1 | Out-String
    $found = [regex]::Matches($logs, 'https://[a-z0-9-]+\.trycloudflare\.com') |
        ForEach-Object { $_.Value } |
        Where-Object { $_ -ne 'https://api.trycloudflare.com' }
    if ($found) { return @($found)[-1] }
    return $null
}

$url = $null
for ($i = 0; $i -le $WaitSeconds; $i++) {
    $url = Get-TunnelUrl
    if ($url) { break }
    if ($i -lt $WaitSeconds) { Start-Sleep -Seconds 1 }
}

if (-not $url) {
    Write-Host "No tunnel URL yet. Check: $Docker compose logs tunnel" -ForegroundColor Yellow
    exit 1
}

Write-Host ''
Write-Host '===================================================' -ForegroundColor Green
Write-Host '  Cloudflare Tunnel is LIVE - open from any device:' -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Cyan
Write-Host '  (first page load can take ~20s while Vite warms up)' -ForegroundColor DarkGray
Write-Host '===================================================' -ForegroundColor Green
Write-Host ''
