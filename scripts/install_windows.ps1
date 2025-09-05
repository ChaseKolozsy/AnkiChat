Param(
    [string]$ImageName = ${env:IMAGE_NAME} ? ${env:IMAGE_NAME} : 'anki-api',
    [string]$ContainerName = ${env:CONTAINER_NAME} ? ${env:CONTAINER_NAME} : 'anki-api',
    [int]$HostPort = ${env:HOST_PORT} ? [int]${env:HOST_PORT} : 5001,
    [string]$HostAnki2Dir = ${env:HOST_ANKI2_DIR} ? ${env:HOST_ANKI2_DIR} : (Join-Path $env:APPDATA 'Anki2'),
    [switch]$SkipPythonInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Info($msg) { Write-Host $msg -ForegroundColor Cyan }
function Warn($msg) { Write-Warning $msg }
function Fail($msg) { Write-Error $msg; exit 1 }

# Validate Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed or not in PATH. Please install Docker Desktop for Windows."
}

# Validate Git
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git is not installed or not in PATH. Please install Git for Windows."
}

# Ensure repo structure present
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$ankiApiDir = Join-Path $repoRoot 'AnkiApi'
$ankiDir = Join-Path $ankiApiDir 'anki'
$dockerDir = Join-Path $ankiApiDir 'docker'

if (-not (Test-Path $ankiApiDir)) { Fail "Missing AnkiApi directory at $ankiApiDir" }
if (-not (Test-Path $ankiDir)) { Fail "Missing Anki source at $ankiDir (submodule). Run: git submodule update --init --recursive" }
if (-not (Test-Path $dockerDir)) { Fail "Missing docker directory at $dockerDir" }

# Resolve Anki commit
try {
    $ankiCommit = (git -C $ankiDir rev-parse HEAD).Trim()
} catch {
    Fail "Failed to determine Anki commit in $ankiDir: $_"
}
Info "Target Anki commit: $ankiCommit"

# Build base image if missing
$baseTag = "anki-core:$ankiCommit"
$baseExists = (& docker image inspect $baseTag *> $null; $LASTEXITCODE -eq 0)
if (-not $baseExists) {
    Info "Building base image $baseTag"
    & docker build --no-cache `
        --tag $baseTag `
        --build-arg "ANKI_COMMIT=$ankiCommit" `
        --file (Join-Path $dockerDir 'Dockerfile.base') `
        $ankiApiDir
} else {
    Info "Using cached base image $baseTag"
}

# Build app image
Info "Building app image $ImageName"
& docker build `
    --tag $ImageName `
    --build-arg "ANKI_COMMIT=$ankiCommit" `
    --file (Join-Path $dockerDir 'Dockerfile.app') `
    $ankiApiDir

# Prepare host mount
if (-not (Test-Path $HostAnki2Dir)) {
    try { New-Item -ItemType Directory -Path $HostAnki2Dir -Force | Out-Null } catch { Warn "Could not create $HostAnki2Dir: $_" }
}
Info "Mounting host collection: $HostAnki2Dir -> /home/anki/.local/share/Anki2"

# Replace container if exists and run
& docker rm -f $ContainerName *> $null
Info "Starting container $ContainerName on port $HostPort -> 5001"
& docker run -d --restart unless-stopped `
    -p "$HostPort:5001" `
    -e "HTTP_PROXY=" -e "HTTPS_PROXY=" -e "ALL_PROXY=" `
    -e "NO_PROXY=sync.ankiweb.net,localhost,127.0.0.1" `
    -v "$HostAnki2Dir:/home/anki/.local/share/Anki2" `
    --cpus=1 `
    --name $ContainerName `
    $ImageName

if (-not $SkipPythonInstall) {
    # Optional: install the Python package locally using uv if available
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        Push-Location $repoRoot
        try { & uv pip install . } catch { Warn "uv pip install failed: $_" }
        Pop-Location
    } else {
        Warn "uv not found; skipping local Python package install."
    }
}

Info "Done. API should be reachable at http://localhost:$HostPort/api"
