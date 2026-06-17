# PyNet Bridge - MCP Server Installer
# Installs pynet-mcp-bridge and configures all detected AI clients:
#   Claude Desktop, Claude Code (VS Code), Cline, Roo Code, Codex, GitHub Copilot

function Add-McpServer($configPath, $createEmpty, $rootKey = "mcpServers", $command = "pynet-bridge") {
    try {
        if (Test-Path $configPath) {
            $raw = [System.IO.File]::ReadAllText($configPath, [System.Text.Encoding]::UTF8)
        } elseif ($createEmpty) {
            $raw = '{}'
        } else {
            return $false
        }

        $cmd = $command -replace '\\', '/'
        $entryJson = "`"pynet-bridge`":{`"type`":`"stdio`",`"command`":`"$cmd`",`"args`":[]}"

        if ($raw -match '"pynet-bridge"\s*:') {
            $raw = [regex]::Replace($raw, '"pynet-bridge"\s*:\s*\{[^{}]*\}', $entryJson)
        } elseif ($raw -match "`"$rootKey`"\s*:\s*\{") {
            $raw = [regex]::Replace($raw, "(`"$rootKey`"\s*:\s*\{)", "`$1$entryJson,")
        } elseif ($raw -match '^\s*\{\s*\}\s*$') {
            $raw = "{`"$rootKey`":{$entryJson}}"
        } elseif ($raw -match '^\s*\{') {
            $raw = [regex]::Replace($raw, '^\s*\{', "{`"$rootKey`":{$entryJson},")
        } else {
            $raw = "{`"$rootKey`":{$entryJson}}"
        }

        $configDir = Split-Path $configPath
        if ($configDir -and -not (Test-Path $configDir)) { New-Item -ItemType Directory -Path $configDir -Force | Out-Null }

        [System.IO.File]::WriteAllText($configPath, $raw, [System.Text.UTF8Encoding]::new($false))
        return $true
    } catch {
        Write-Host "  WARNING: Could not configure $configPath" -ForegroundColor DarkYellow
        return $false
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   PyNet Bridge - MCP Server Installer  " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# --- Step 1: Check Python >= 3.10 ---
Write-Host "Checking Python installation..." -ForegroundColor Yellow
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Python not found. Install Python 3.10+ from https://python.org and try again." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

$pythonVersion = python --version
Write-Host "Found: $pythonVersion" -ForegroundColor Green

$versionMatch = [regex]::Match($pythonVersion, '(\d+)\.(\d+)')
if ($versionMatch.Success) {
    $major = [int]$versionMatch.Groups[1].Value
    $minor = [int]$versionMatch.Groups[2].Value
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Host "ERROR: Python 3.10+ is required but found $major.$minor. Please upgrade." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Host "WARNING: Could not determine Python version. Proceeding anyway..." -ForegroundColor DarkYellow
}

# --- Step 2: Ensure uv is installed ---
Write-Host ""
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found. Installing uv..." -ForegroundColor Yellow
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "User") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "Machine")
    } catch {
        Write-Host "WARNING: Could not install uv automatically. Falling back to pip." -ForegroundColor DarkYellow
    }
}

# --- Step 3: Install package ---
$hasUv = [bool](Get-Command uv -ErrorAction SilentlyContinue)

if ($hasUv) {
    Write-Host "Installing pynet-mcp-bridge via uv..." -ForegroundColor Yellow
    uv tool install pynet-mcp-bridge --upgrade --quiet
} else {
    Write-Host "Installing pynet-mcp-bridge via pip..." -ForegroundColor DarkYellow
    pip install pynet-mcp-bridge --upgrade --quiet
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Installation failed. Check your internet connection and try again." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "Package installed successfully." -ForegroundColor Green

# --- Step 4: Resolve installed executable ---
Write-Host ""
Write-Host "Resolving pynet-bridge executable..." -ForegroundColor Yellow
$bridgeCommand = (Get-Command pynet-bridge -ErrorAction SilentlyContinue).Source

if (-not $bridgeCommand) {
    Write-Host "ERROR: pynet-bridge was installed but not found." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Using command: $bridgeCommand" -ForegroundColor Green

# --- Step 5: Auto-detect and configure AI clients ---
Write-Host ""
Write-Host "Detecting installed AI clients..." -ForegroundColor Yellow

$configured = 0

# -- Claude Desktop --
$storePkg = Get-ChildItem "$env:LOCALAPPDATA\Packages" -Filter "Claude_*" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($storePkg) {
    $desktopConfig = "$($storePkg.FullName)\LocalCache\Roaming\Claude\claude_desktop_config.json"
} elseif (Test-Path "$env:APPDATA\Claude") {
    $desktopConfig = "$env:APPDATA\Claude\claude_desktop_config.json"
} else {
    $desktopConfig = $null
}

if ($desktopConfig) {
    $ok = Add-McpServer $desktopConfig $true
    if ($ok) { Write-Host "  [OK] Claude Desktop" -ForegroundColor Green; $configured++ }
} else {
    Write-Host "  [--] Claude Desktop: not found" -ForegroundColor DarkGray
}

# -- Claude Code --
$ok = Add-McpServer "$env:USERPROFILE\.claude.json" $true
if ($ok) { Write-Host "  [OK] Claude Code" -ForegroundColor Green; $configured++ }

# -- Cline --
$clinePath = "$env:APPDATA\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json"
if (Test-Path (Split-Path $clinePath)) {
    $ok = Add-McpServer $clinePath $true
    if ($ok) { Write-Host "  [OK] Cline" -ForegroundColor Green; $configured++ }
} else {
    Write-Host "  [--] Cline: not found" -ForegroundColor DarkGray
}

# -- Roo Code --
$rooPath = "$env:APPDATA\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\mcp_settings.json"
if (Test-Path (Split-Path $rooPath)) {
    $ok = Add-McpServer $rooPath $true
    if ($ok) { Write-Host "  [OK] Roo Code" -ForegroundColor Green; $configured++ }
} else {
    Write-Host "  [--] Roo Code: not found" -ForegroundColor DarkGray
}

# -- Codex --
$codexPath = "$env:USERPROFILE\.codex\config.toml"

$block = @(
    "[mcp_servers.pynet-bridge]"
    "command = ""$($bridgeCommand -replace '\\','/')"""
    "args = []"
) -join "`r`n"

$content = if (Test-Path $codexPath) {
    [System.IO.File]::ReadAllText($codexPath, [System.Text.Encoding]::UTF8)
} else { "" }

$pattern = '(?ms)^\[mcp_servers\.pynet-bridge\]\s*.*?(?=^\[|\z)'

if ([regex]::IsMatch($content, $pattern)) {
    $content = [regex]::Replace($content, $pattern, $block + "`r`n`r`n")
} else {
    $content += "`r`n" + $block + "`r`n"
}

$codexDir = Split-Path $codexPath
if (-not (Test-Path $codexDir)) { New-Item -ItemType Directory -Path $codexDir | Out-Null }
[System.IO.File]::WriteAllText($codexPath, $content, [System.Text.UTF8Encoding]::new($false))
Write-Host "  [OK] Codex" -ForegroundColor Green
$configured++

# -- GitHub Copilot (VS Code) --
# Copilot reads a dedicated user-level MCP file with the "servers" root key (not "mcpServers").
$copilotPath = "$env:APPDATA\Code\User\mcp.json"
if (Test-Path "$env:APPDATA\Code\User") {
    $ok = Add-McpServer $copilotPath $true "servers" $bridgeCommand
    if ($ok) { Write-Host "  [OK] GitHub Copilot" -ForegroundColor Green; $configured++ }
} else {
    Write-Host "  [--] GitHub Copilot: VS Code not found" -ForegroundColor DarkGray
}

# --- Done ---
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "   Installation complete!" -ForegroundColor Green
Write-Host "   Configured $configured client(s)." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"