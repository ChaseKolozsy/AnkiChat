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

# Install Node.js 18+ and npm if not present or version is too old
Info "Checking Node.js version..."
$nodeInstalled = Get-Command node -ErrorAction SilentlyContinue
if ($nodeInstalled) {
    $nodeVersion = (node --version) -replace 'v(\d+)\..*', '$1'
    if ([int]$nodeVersion -lt 18) {
        Info "Node.js version is less than 18. Installing Node.js 20..."
        # Download and install Node.js 20
        $nodeUrl = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi"
        $nodeInstaller = "$env:TEMP\node-installer.msi"
        Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeInstaller
        Start-Process msiexec.exe -ArgumentList "/i", $nodeInstaller, "/quiet" -Wait
        Remove-Item $nodeInstaller
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    } else {
        Info "Node.js version $nodeVersion is already installed."
    }
} else {
    Info "Node.js not found. Installing Node.js 20..."
    # Download and install Node.js 20
    $nodeUrl = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi"
    $nodeInstaller = "$env:TEMP\node-installer.msi"
    Invoke-WebRequest -Uri $nodeUrl -OutFile $nodeInstaller
    Start-Process msiexec.exe -ArgumentList "/i", $nodeInstaller, "/quiet" -Wait
    Remove-Item $nodeInstaller
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
}

# Install Claude Code globally via npm
Info "Installing Claude Code..."
& npm install -g @anthropic-ai/claude-code

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
    # Install uv if not present
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Info "Installing uv..."
        Invoke-RestMethod -Uri https://astral.sh/uv/install.ps1 | Invoke-Expression
    }
    
    # Clear uv cache before installation
    Info "Clearing uv cache..."
    & uv cache clean
    
    # Install AnkiChat globally as a uv tool
    Info "Installing AnkiChat globally as a uv tool..."
    Push-Location $repoRoot
    try { 
        & uv tool install . --force 
        Info "AnkiChat installed successfully as global uv tool"
        
        # Verify installation
        Info "Verifying AnkiChat installation..."
        & uv tool list | Select-String "anki-chat"
    } catch { 
        Warn "uv tool install failed: $_" 
    }
    Pop-Location
    
    # Configure Claude Code with AnkiChat MCP server
    Info "Configuring Claude Code with AnkiChat MCP server..."
    $mcpConfigPath = Join-Path $repoRoot "mcp_config_global.json"
    
    if (Test-Path $mcpConfigPath) {
        Info "Adding AnkiChat MCP server to Claude Code..."
        # Add the MCP server at project level using the latest method
        # On Windows, we need to use cmd /c for npx-based commands
        Push-Location $repoRoot
        try {
            & claude mcp add anki-chat --scope project -- anki-chat-mcp
            Info "MCP server configured successfully."
        } catch {
            Warn "Failed to configure MCP server: $_"
        }
        Pop-Location
    } else {
        Warn "mcp_config_global.json not found at $mcpConfigPath"
    }
}

Info "Installation complete!"
Info "API should be reachable at http://localhost:$HostPort/api"
Info "You can now use 'claude' command to access Claude Code with AnkiChat MCP integration."
