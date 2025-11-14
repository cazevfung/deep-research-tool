<#
.SYNOPSIS
    Launch the Research Tool backend and frontend dev servers with one command.

.DESCRIPTION
    This script mirrors the manual steps we follow when debugging:
      1. Start the FastAPI backend with `python backend/run_server.py` from the project root.
      2. Start the Vite frontend dev server with `npm run dev` from the `client` directory.

    Each process is launched in its own PowerShell window so their logs remain visible.

.NOTES
    Run from anywhere:
        powershell -ExecutionPolicy Bypass -File backend\start_dev.ps1
#>

param(
    [switch] $NoFrontend
)

function Assert-CommandExists {
    param(
        [Parameter(Mandatory)][string] $CommandName,
        [string] $InstallHint
    )

    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        $hint = if ($InstallHint) { "`n$InstallHint" } else { "" }
        throw "Required command '$CommandName' was not found in PATH.$hint"
    }
}

try {
    # Resolve important paths
    $scriptDir   = Split-Path -LiteralPath $PSCommandPath -Parent
    $projectRoot = Resolve-Path -LiteralPath (Join-Path $scriptDir "..")
    $clientDir   = Join-Path $projectRoot "client"

    Write-Host "Project root : $projectRoot"
    Write-Host "Backend dir  : $scriptDir"
    Write-Host "Client dir   : $clientDir"
    Write-Host ""

    # Ensure required commands exist
    Assert-CommandExists -CommandName "python" `
        -InstallHint "Install Python 3 and ensure it is available in PATH."
    Assert-CommandExists -CommandName "npm" `
        -InstallHint "Install Node.js (which includes npm) and ensure it is available in PATH."

    # Launch backend server in a new PowerShell window
    $backendCmd = @"
cd '$projectRoot'
Write-Host 'Starting backend server...' -ForegroundColor Cyan
python backend/run_server.py
"@

    Write-Host "Launching backend server window..."
    Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $backendCmd `
        -WorkingDirectory $projectRoot

    if (-not $NoFrontend) {
        if (-not (Test-Path -LiteralPath $clientDir)) {
            throw "Client directory not found at '$clientDir'."
        }

        # Launch frontend dev server in a new PowerShell window
        $frontendCmd = @"
cd '$clientDir'
Write-Host 'Starting frontend dev server (Vite)...' -ForegroundColor Cyan
npm run dev
"@

        Write-Host "Launching frontend dev server window..."
        Start-Process -FilePath "powershell" -ArgumentList "-NoExit", "-Command", $frontendCmd `
            -WorkingDirectory $clientDir
    }
    else {
        Write-Host "Frontend launch skipped because -NoFrontend was specified." -ForegroundColor Yellow
    }

    Write-Host ""
    Write-Host "Both servers are starting. Keep the spawned PowerShell windows open to view logs."
    if (-not $NoFrontend) {
        Write-Host "Open http://localhost:3000 once both windows report they are ready."
    } else {
        Write-Host "Backend is starting. Frontend launch was skipped."
    }
}
catch {
    Write-Error $_
    exit 1
}




