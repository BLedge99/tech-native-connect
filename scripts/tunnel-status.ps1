# Resolve and verify the live Cloudflare Quick Tunnel URL.
#
# Lives in a script rather than inline in run.bat because the logic is two
# non-obvious steps and batch quoting mangles both of them.
#
#   -Mode tunnel   wait for the tunnel, print the banner
#   -Mode url      print the URL only (run.bat url)

param(
    [ValidateSet('tunnel', 'url')]
    [string]$Mode = 'url',
    [string]$DockerExe = 'docker',
    # 'docker' when going through WSL, empty when docker is on PATH. Building
    # the argument list conditionally matters: passing an empty prefix through
    # as a real argument turns the command into `docker '' compose`.
    [string]$DockerPrefix = '',
    [int]$TimeoutSeconds = 60
)

# Built conditionally. `docker docker compose` — what an unconditional prefix
# produced — exits with "unknown command", the log comes back empty, and the
# script reports "no tunnel URL" while one is running and healthy.
$dockerArgs = @()
if ($DockerPrefix) { $dockerArgs += $DockerPrefix }
$dockerArgs += @('compose', 'logs', 'tunnel')

# Compose logs the tunnel service's ENTIRE history, not just this run, so every
# hostname the container has ever printed is in this string.
$logs = & $DockerExe @dockerArgs 2>&1 | Out-String

# Take the LAST match, not the first. A restarted cloudflared is handed a new
# random hostname while the dead one stays in the log history; printing the
# first match is how you hand a marker a dead URL that answers Cloudflare
# error 1033 ("edge knows the hostname, no cloudflared is registered for it").
$urls = [regex]::Matches($logs, 'https://[a-zA-Z0-9-]+\.trycloudflare\.com')

if ($urls.Count -eq 0) {
    Write-Host 'No tunnel URL found in the tunnel log.' -ForegroundColor Yellow
    Write-Host "  ran: $DockerExe $($dockerArgs -join ' ')" -ForegroundColor DarkGray
    if ([string]::IsNullOrWhiteSpace($logs)) {
        Write-Host '  That command returned NOTHING - docker failed, or the tunnel' -ForegroundColor Yellow
        Write-Host '  container does not exist in this project.' -ForegroundColor Yellow
    } else {
        Write-Host "  It returned $($logs.Length) chars with no trycloudflare.com URL in it." -ForegroundColor Yellow
        Write-Host '  The tunnel is probably still starting. Wait and run again.' -ForegroundColor Yellow
    }
    Write-Host "  $DockerExe $($dockerArgs -join ' ') ps tunnel" -ForegroundColor DarkGray
    exit 1
}

$url = $urls[$urls.Count - 1].Value

# Only in tunnel mode: do not claim it is live until Cloudflare's edge actually
# routes to it. The log line appears before the tunnel is registered on every
# colo, so printing a green banner on the log line alone is a coin flip.
if ($Mode -eq 'url') {
    Write-Host $url -ForegroundColor Cyan
    exit 0
}

Write-Host "Tunnel URL: $url" -ForegroundColor DarkGray
Write-Host 'Checking it serves traffic...'

# Windows PowerShell 5.1 runs on .NET Framework, whose default protocol set on
# a lot of machines still excludes TLS 1.2. Cloudflare requires it, so the
# request fails with a TLS error that looks nothing like a tunnel problem.
try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
} catch { }

$live = $false
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$lastError = ''
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -Uri "$url/api/v1/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) { $live = $true; break }
        $lastError = "HTTP $($response.StatusCode)"
    } catch {
        $lastError = $_.Exception.Message
    }
    Start-Sleep -Seconds 2
}

if ($live) {
    Write-Host ''
    Write-Host '===================================================' -ForegroundColor Green
    Write-Host '  Cloudflare Tunnel is LIVE! Open to web traffic:  ' -ForegroundColor Green
    Write-Host "  $url" -ForegroundColor Cyan
    Write-Host '===================================================' -ForegroundColor Green
    Write-Host ''
    exit 0
}

# Not serving. Say so rather than printing a confident banner over a dead URL.
Write-Host ''
Write-Host '===================================================' -ForegroundColor Yellow
Write-Host '  Tunnel URL is NOT serving traffic yet:          ' -ForegroundColor Yellow
Write-Host "  $url" -ForegroundColor Cyan
Write-Host '===================================================' -ForegroundColor Yellow
Write-Host "Checked $url/api/v1/health for $TimeoutSeconds s and got no 200." -ForegroundColor Yellow
if ($lastError) { Write-Host "  last error: $lastError" -ForegroundColor DarkGray }
Write-Host 'Either the tunnel is still registering, or it died. Check:' -ForegroundColor Yellow
Write-Host "  $DockerExe $($dockerArgs -join ' ') ps tunnel" -ForegroundColor DarkGray
exit 1