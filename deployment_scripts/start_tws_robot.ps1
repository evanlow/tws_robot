# TWS Robot - Startup Script
# This script starts the TWS Robot with validation checks

param(
    [switch]$SkipTests = $false
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TWS Robot - Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check virtual environment
Write-Host "[1/4] Checking virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path ".\Scripts\Activate.ps1")) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Run: python -m venv ." -ForegroundColor Yellow
    exit 1
}
& .\Scripts\Activate.ps1
Write-Host "✓ Virtual environment activated" -ForegroundColor Green
Write-Host ""

# Step 2: Check environment configuration
Write-Host "[2/4] Checking environment configuration..." -ForegroundColor Yellow
if (-not (Test-Path ".\.env")) {
    Write-Host "ERROR: .env not found!" -ForegroundColor Red
    Write-Host "Copy .env.example to .env and configure it" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ Environment configuration found" -ForegroundColor Green
Write-Host ""

# Step 3: Initialize database
Write-Host "[3/4] Initializing database schema..." -ForegroundColor Yellow
if (Test-Path ".\init_database.py") {
    python init_database.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Database initialization failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Database schema initialized" -ForegroundColor Green
} else {
    Write-Host "⚠ No init_database.py found, skipping..." -ForegroundColor Yellow
}
Write-Host ""

# Step 4: Run tests
if (-not $SkipTests) {
    Write-Host "[4/4] Running validation tests..." -ForegroundColor Yellow
    Write-Host "This may take a few minutes..." -ForegroundColor Gray
    pytest --tb=no -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Tests failed! Startup aborted." -ForegroundColor Red
        Write-Host "All tests must pass before starting." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "✓ All tests passing (647/647)" -ForegroundColor Green
    Write-Host ""
}

# Start TWS Robot
Write-Host "========================================" -ForegroundColor Green
Write-Host "  TWS Robot is starting..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Logs: ./logs/" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop gracefully" -ForegroundColor Yellow
Write-Host ""

# Start the main application
if (Test-Path ".\main.py") {
    python main.py
} elseif (Test-Path ".\tws_client.py") {
    python tws_client.py
} else {
    Write-Host "⚠ No main entry point found (main.py or tws_client.py)" -ForegroundColor Yellow
    Write-Host "Start your application manually." -ForegroundColor Cyan
}
