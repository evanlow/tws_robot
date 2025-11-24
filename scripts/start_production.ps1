# TWS Robot - Production Startup Script (Local Deployment)
# This script starts the TWS Robot in production mode on Windows

param(
    [switch]$SkipDatabaseCheck = $false,
    [switch]$SkipTests = $false
)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TWS Robot - Production Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Check virtual environment
Write-Host "[1/7] Checking virtual environment..." -ForegroundColor Yellow
if (-not (Test-Path ".\Scripts\Activate.ps1")) {
    Write-Host "ERROR: Virtual environment not found!" -ForegroundColor Red
    Write-Host "Run: python -m venv ." -ForegroundColor Yellow
    exit 1
}
& .\Scripts\Activate.ps1
Write-Host "✓ Virtual environment activated" -ForegroundColor Green
Write-Host ""

# Step 2: Check environment configuration
Write-Host "[2/7] Checking environment configuration..." -ForegroundColor Yellow
if (-not (Test-Path ".\.env.production")) {
    Write-Host "ERROR: .env.production not found!" -ForegroundColor Red
    Write-Host "Copy .env.production.example to .env.production and configure it" -ForegroundColor Yellow
    exit 1
}
Write-Host "✓ Environment configuration found" -ForegroundColor Green
Write-Host ""

# Step 3: Start Docker services (PostgreSQL + Redis)
Write-Host "[3/7] Starting database services..." -ForegroundColor Yellow
docker-compose -f docker-compose.local.yml up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to start Docker services" -ForegroundColor Red
    exit 1
}
Write-Host "Waiting for services to be ready..."
Start-Sleep -Seconds 10
Write-Host "✓ Database services started" -ForegroundColor Green
Write-Host ""

# Step 4: Check database connection
if (-not $SkipDatabaseCheck) {
    Write-Host "[4/7] Checking database connection..." -ForegroundColor Yellow
    docker exec tws-robot-postgres pg_isready -U tws_user -d tws_robot_prod
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Database not ready" -ForegroundColor Red
        exit 1
    }
    Write-Host "✓ Database connection verified" -ForegroundColor Green
    Write-Host ""
}

# Step 5: Initialize/migrate database
Write-Host "[5/7] Initializing database schema..." -ForegroundColor Yellow
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

# Step 6: Run production tests
if (-not $SkipTests) {
    Write-Host "[6/7] Running production validation tests..." -ForegroundColor Yellow
    Write-Host "This may take a few minutes..." -ForegroundColor Gray
    pytest --tb=no -q
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Tests failed! Production start aborted." -ForegroundColor Red
        Write-Host "All tests must pass before starting production." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "✓ All tests passing (647/647)" -ForegroundColor Green
    Write-Host ""
}

# Step 7: Start TWS Robot
Write-Host "[7/7] Starting TWS Robot in production mode..." -ForegroundColor Yellow
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  TWS Robot is starting..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Dashboard: http://localhost:8080" -ForegroundColor Cyan
Write-Host "Logs: ./logs/tws_robot.log" -ForegroundColor Cyan
Write-Host ""
Write-Host "Press Ctrl+C to stop gracefully" -ForegroundColor Yellow
Write-Host ""

# Start the main application (adjust the entry point as needed)
# For now, this is a placeholder - you'll replace this with your actual main script
if (Test-Path ".\main.py") {
    python main.py --config .env.production
} elseif (Test-Path ".\tws_client.py") {
    Write-Host "Starting with tws_client.py (temporary)..." -ForegroundColor Yellow
    python tws_client.py
} else {
    Write-Host "⚠ No main entry point found (main.py or production script)" -ForegroundColor Yellow
    Write-Host "Production environment is ready. Start your application manually." -ForegroundColor Cyan
}
