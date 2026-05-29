# VectoSports AI Results Server - Development Helper Script (Windows)
# Usage: .\dev.ps1 build|up|down|logs|test|help

param(
    [Parameter(Position = 0)]
    [string]$Command = "help"
)

# Colors
$Green = "Green"
$Yellow = "Yellow"
$Red = "Red"

function Print-Header {
    param([string]$Text)
    Write-Host "`n================================" -ForegroundColor $Green
    Write-Host $Text -ForegroundColor $Green
    Write-Host "================================`n" -ForegroundColor $Green
}

function Print-Step {
    param([string]$Text)
    Write-Host "▶ $Text" -ForegroundColor $Yellow
}

function Print-Success {
    param([string]$Text)
    Write-Host "✓ $Text" -ForegroundColor $Green
}

function Print-Error {
    param([string]$Text)
    Write-Host "✗ $Text" -ForegroundColor $Red
}

switch ($Command) {
    "build" {
        Print-Header "Building Docker Image"
        Print-Step "Running: docker-compose build"
        docker-compose build
        Print-Success "Build completed"
    }
    
    "up" {
        Print-Header "Starting Docker Container"
        Print-Step "Running: docker-compose up -d"
        docker-compose up -d
        Print-Success "Container started"
        Print-Success "Container started"
    }
    
    "down" {
        Print-Header "Stopping Docker Container"
        Print-Step "Running: docker-compose down"
        docker-compose down
        Print-Success "Container stopped"
    }
    
    "logs" {
        Print-Header "Docker Logs"
        docker-compose logs -f vectosports-ai-server
    }
    
    "logs-tail" {
        Print-Header "Last 50 Lines of Logs"
        docker-compose logs --tail=50 vectosports-ai-server
    }
    
    "restart" {
        Print-Header "Restarting Docker Container"
        Print-Step "Stopping..."
        docker-compose down
        Print-Step "Starting..."
        docker-compose up -d
        Start-Sleep -Seconds 2
        Print-Success "Container restarted"
    }
    
    "clean" {
        Print-Header "Cleaning Up"
        Print-Step "Removing containers..."
        docker-compose down
        Print-Step "Removing data..."
        if (Test-Path "./data/uploads") {
            Remove-Item "./data/uploads/*" -Recurse -Force
        }
        New-Item -ItemType Directory -Path "./data/uploads" -Force | Out-Null
        Print-Success "Cleanup completed"
    }
    
    "test" {
        Print-Header "Running Tests"
        Print-Step "Installing test dependencies..."
        python -m pip install requests -q
        Print-Step "Running test suite..."
        python test_api.py
    }
    
    "health" {
        Print-Header "Health Check"
        Print-Step "Checking server health..."
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -TimeoutSec 5 -UseBasicParsing
            $json = $response.Content | ConvertFrom-Json
            $json | ConvertTo-Json | Write-Host
        }
        catch {
            Print-Error "Server not responding"
        }
    }
    
    "debug-sessions" {
        Print-Header "Active Upload Sessions"
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/debug/sessions" -TimeoutSec 5 -UseBasicParsing
            $response.Content | ConvertFrom-Json | ConvertTo-Json | Write-Host
        }
        catch {
            Print-Error "Cannot fetch sessions"
        }
    }
    
    "debug-jobs" {
        Print-Header "Active Jobs"
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:8000/debug/jobs" -TimeoutSec 5 -UseBasicParsing
            $response.Content | ConvertFrom-Json | ConvertTo-Json | Write-Host
        }
        catch {
            Print-Error "Cannot fetch jobs"
        }
    }
    
    "ps" {
        Print-Header "Docker Container Status"
        docker-compose ps
    }
    
    "shell" {
        Print-Header "Opening Container Shell"
        docker-compose exec vectosports-ai-server /bin/bash
    }
    
    "install-deps" {
        Print-Header "Installing Python Dependencies"
        Print-Step "Installing local dependencies for development..."
        python -m pip install -r api/requirements.txt
        Print-Success "Dependencies installed"
    }
    
    "lint" {
        Print-Header "Code Linting"
        $pylintExists = Get-Command pylint -ErrorAction SilentlyContinue
        if (-not $pylintExists) {
            Print-Step "Installing pylint..."
            python -m pip install pylint -q
        }
        Print-Step "Running pylint on server.py..."
        pylint api/server.py
    }
    
    "format" {
        Print-Header "Code Formatting"
        $blackExists = Get-Command black -ErrorAction SilentlyContinue
        if (-not $blackExists) {
            Print-Step "Installing black..."
            python -m pip install black -q
        }
        Print-Step "Formatting api/server.py..."
        black api/server.py
        Print-Success "Code formatted"
    }
    
    { $_ -in "help", "--help", "-h" } {
        Print-Header "VectoSports AI Results Server - Helper Commands"
        Write-Host "Usage: .\dev.ps1 [COMMAND]" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "Commands:" -ForegroundColor Cyan
        Write-Host "  build              Build Docker image"
        Write-Host "  up                 Start Docker container"
        Write-Host "  down               Stop Docker container"
        Write-Host "  restart            Restart Docker container"
        Write-Host "  logs               Show logs (follow)"
        Write-Host "  logs-tail          Show last 50 lines of logs"
        Write-Host "  clean              Stop container and clean data"
        Write-Host "  ps                 Show container status"
        Write-Host "  shell              Open container shell"
        Write-Host ""
        Write-Host "Testing & Debug:" -ForegroundColor Cyan
        Write-Host "  test               Run full test suite"
        Write-Host "  health             Check server health"
        Write-Host "  debug-sessions     List active upload sessions"
        Write-Host "  debug-jobs         List active jobs"
        Write-Host ""
        Write-Host "Development:" -ForegroundColor Cyan
        Write-Host "  install-deps       Install Python dependencies"
        Write-Host "  lint               Lint code with pylint"
        Write-Host "  format             Format code with black"
        Write-Host ""
        Write-Host "Help:" -ForegroundColor Cyan
        Write-Host "  help               Show this help message"
        Write-Host ""
        Print-Success "For more info, see API_SERVER_README.md"
    }
    
    default {
        Print-Error "Unknown command: $Command"
        Write-Host "Run '.\dev.ps1 help' for available commands"
        exit 1
    }
}
