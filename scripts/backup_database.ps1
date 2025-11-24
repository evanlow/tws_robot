# TWS Robot - Database Backup Script (Local Deployment)

param(
    [string]$BackupDir = "./backups"
)

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = "tws_robot_backup_$Timestamp.sql"
$BackupPath = Join-Path $BackupDir $BackupFile

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  TWS Robot - Database Backup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Create backup directory if it doesn't exist
if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
    Write-Host "✓ Created backup directory: $BackupDir" -ForegroundColor Green
}

Write-Host "Creating database backup..." -ForegroundColor Yellow
Write-Host "Backup file: $BackupFile" -ForegroundColor Gray
Write-Host ""

# Create backup using pg_dump in Docker container
docker exec tws-robot-postgres pg_dump -U tws_user -d tws_robot_prod -F p -f "/backups/$BackupFile"

if ($LASTEXITCODE -eq 0) {
    Write-Host "✓ Database backup completed successfully" -ForegroundColor Green
    Write-Host ""
    Write-Host "Backup location: $BackupPath" -ForegroundColor Cyan
    
    # Get backup file size
    if (Test-Path $BackupPath) {
        $Size = (Get-Item $BackupPath).Length / 1KB
        Write-Host "Backup size: $([math]::Round($Size, 2)) KB" -ForegroundColor Cyan
    }
    
    # Optional: Clean up old backups (keep last 30 days)
    Write-Host ""
    Write-Host "Cleaning up old backups (keeping last 30 days)..." -ForegroundColor Yellow
    $CutoffDate = (Get-Date).AddDays(-30)
    Get-ChildItem -Path $BackupDir -Filter "tws_robot_backup_*.sql" | 
        Where-Object { $_.LastWriteTime -lt $CutoffDate } | 
        ForEach-Object {
            Remove-Item $_.FullName
            Write-Host "  Deleted old backup: $($_.Name)" -ForegroundColor Gray
        }
    
    Write-Host "✓ Backup cleanup complete" -ForegroundColor Green
} else {
    Write-Host "ERROR: Database backup failed" -ForegroundColor Red
    exit 1
}
