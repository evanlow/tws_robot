# TWS Robot - Production Shutdown Script (Local Deployment)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TWS Robot - Graceful Shutdown" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "Stopping TWS Robot application..." -ForegroundColor Yellow
Write-Host "(Ctrl+C the running process if needed)" -ForegroundColor Gray
Write-Host ""

Write-Host "Stopping Docker services..." -ForegroundColor Yellow
docker-compose -f docker-compose.local.yml down

Write-Host ""
Write-Host "✓ Production environment stopped" -ForegroundColor Green
Write-Host ""
Write-Host "Database data persisted in Docker volumes" -ForegroundColor Cyan
Write-Host "To restart: .\scripts\start_production.ps1" -ForegroundColor Cyan
