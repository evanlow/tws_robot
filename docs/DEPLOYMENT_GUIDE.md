# TWS Robot v2.0 - Deployment & DevOps Guide
## Production Setup and Operations Manual

**Document Version:** 1.1  
**Last Updated:** April 2026  
**Operations Team:** DevOps & Production Support  

---

> ⚠️ **IMPORTANT NOTICE**
> 
> **This deployment guide describes a planned production architecture that is partially implemented.**
> 
> The Docker configurations, FastAPI gateway, and full production infrastructure
> described in this document represent the **future production roadmap** for TWS Robot.
> 
> **Current Project Status:**
> - ✅ **Core backtesting engine** - Fully implemented and tested
> - ✅ **Risk management system** - Production ready
> - ✅ **Strategy templates** - Available for backtesting (MovingAverage, MeanReversion, Momentum)
> - ✅ **Live trading integration** - BollingerBands strategy available for paper/live trading with TWS
> - ✅ **Web dashboard** - Implemented (Flask-based, launch with `python scripts/run_web.py`)
> - ❌ **Docker containerization** - Planned, not yet implemented
> - ❌ **FastAPI gateway** - Planned, not yet implemented
> - ❌ **Production monitoring (Prometheus/Grafana)** - Planned, not yet implemented
> 
> **To use TWS Robot today:**
> - Launch the web dashboard: `python scripts/run_web.py` → http://127.0.0.1:5000
> - Follow the [README.md](../README.md) Quick Start for local development setup
> - Use [USER_GUIDE.md](USER_GUIDE.md) for backtesting and paper trading
> - See [LOCAL_DEPLOYMENT.md](LOCAL_DEPLOYMENT.md) for local deployment with the web dashboard
> 
> **This guide is useful for:**
> - Understanding the planned production architecture
> - Preparing for future deployment
> - Contributing to production infrastructure development

---

## 🚀 Production Deployment Strategy

### **Infrastructure Architecture**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Load Balancer │    │   Web Gateway   │    │   Trading Core  │
│   (Nginx)       │────│   (FastAPI)     │────│   (Python)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Database      │    │   Cache Layer   │    │   Monitoring    │
│   (PostgreSQL)  │    │   (Redis)       │    │   (Prometheus)  │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### **Container Configuration**
```yaml
# docker-compose.production.yml
version: '3.8'

services:
  tws-robot:
    build:
      context: .
      dockerfile: Dockerfile.production
    container_name: tws-robot-core
    restart: unless-stopped
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://user:pass@postgres:5432/tws_robot
      - REDIS_URL=redis://redis:6379
      - TWS_HOST=${TWS_HOST}
      - TWS_PORT=${TWS_PORT}
      - TWS_CLIENT_ID=${TWS_CLIENT_ID}
    volumes:
      - ./config:/app/config:ro
      - ./logs:/app/logs
      - ./data:/app/data
    depends_on:
      - postgres
      - redis
    networks:
      - tws-network
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3

  web-dashboard:
    build:
      context: ./web
      dockerfile: Dockerfile
    container_name: tws-dashboard
    restart: unless-stopped
    ports:
      - "3000:3000"
    environment:
      - REACT_APP_API_URL=http://api-gateway:8000
    depends_on:
      - api-gateway
    networks:
      - tws-network

  api-gateway:
    image: tws-robot:latest
    container_name: tws-api-gateway
    restart: unless-stopped
    command: uvicorn web.app:app --host 0.0.0.0 --port 8000
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/tws_robot
      - REDIS_URL=redis://redis:6379
    depends_on:
      - postgres
      - redis
    networks:
      - tws-network

  postgres:
    image: postgres:15
    container_name: tws-postgres
    restart: unless-stopped
    environment:
      - POSTGRES_DB=tws_robot
      - POSTGRES_USER=${DB_USER}
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    networks:
      - tws-network

  redis:
    image: redis:7-alpine
    container_name: tws-redis
    restart: unless-stopped
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    volumes:
      - redis_data:/data
    ports:
      - "6379:6379"
    networks:
      - tws-network

  nginx:
    image: nginx:alpine
    container_name: tws-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/ssl/certs:ro
    depends_on:
      - web-dashboard
      - api-gateway
    networks:
      - tws-network

  prometheus:
    image: prom/prometheus:latest
    container_name: tws-prometheus
    restart: unless-stopped
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--web.enable-lifecycle'
    networks:
      - tws-network

  grafana:
    image: grafana/grafana:latest
    container_name: tws-grafana
    restart: unless-stopped
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana_data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/var/lib/grafana/dashboards
    networks:
      - tws-network

  backup-service:
    image: tws-robot:latest
    container_name: tws-backup
    restart: unless-stopped
    command: python scripts/backup_service.py
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/tws_robot
      - BACKUP_S3_BUCKET=${BACKUP_S3_BUCKET}
      - AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
      - AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
    volumes:
      - ./backups:/app/backups
    depends_on:
      - postgres
    networks:
      - tws-network

volumes:
  postgres_data:
  redis_data:
  prometheus_data:
  grafana_data:

networks:
  tws-network:
    driver: bridge
```

### **Production Dockerfile**
```dockerfile
# Dockerfile.production
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN groupadd -r tws && useradd -r -g tws tws
RUN chown -R tws:tws /app
USER tws

# Create necessary directories
RUN mkdir -p logs data config

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')"

# Default command
CMD ["python", "main.py"]
```

---

## 🔒 Security & SSL Configuration

### **Nginx SSL Configuration**
```nginx
# nginx/nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream api_backend {
        server api-gateway:8000;
    }

    upstream dashboard_backend {
        server web-dashboard:3000;
    }

    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;

    # Main dashboard
    server {
        listen 80;
        server_name your-domain.com;
        return 301 https://$server_name$request_uri;
    }

    server {
        listen 443 ssl;
        server_name your-domain.com;

        ssl_certificate /etc/ssl/certs/your-domain.crt;
        ssl_certificate_key /etc/ssl/certs/your-domain.key;

        # Dashboard
        location / {
            proxy_pass http://dashboard_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # API routes
        location /api/ {
            proxy_pass http://api_backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # WebSocket support
        location /ws/ {
            proxy_pass http://api_backend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

### **Environment Variables**
```bash
# .env.production
ENVIRONMENT=production

# Database
DB_HOST=postgres
DB_PORT=5432
DB_NAME=tws_robot
DB_USER=tws_user
DB_PASSWORD=secure_password_here

# Redis
REDIS_URL=redis://redis:6379
REDIS_PASSWORD=redis_password_here

# TWS Connection
TWS_HOST=127.0.0.1
TWS_PORT=7497
TWS_CLIENT_ID=1

# Security
JWT_SECRET_KEY=your-super-secret-jwt-key
API_KEY=your-api-key-for-external-access

# Backup & Storage
BACKUP_S3_BUCKET=tws-robot-backups
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret

# Monitoring
GRAFANA_PASSWORD=admin_password
PROMETHEUS_RETENTION=15d

# Alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/your-webhook
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_USERNAME=alerts@yourdomain.com
EMAIL_PASSWORD=your-email-password

# Trading
MAX_DAILY_LOSS=0.02  # 2%
MAX_POSITION_SIZE=0.05  # 5%
RISK_FREE_RATE=0.05  # 5%
```

---

## 📊 Monitoring & Alerting

### **Prometheus Configuration**
```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alert_rules.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets:
          - alertmanager:9093

scrape_configs:
  - job_name: 'tws-robot'
    static_configs:
      - targets: ['tws-robot:8000']
    metrics_path: '/metrics'
    scrape_interval: 5s

  - job_name: 'postgres'
    static_configs:
      - targets: ['postgres:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:9121']

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']
```

### **Alert Rules**
```yaml
# monitoring/alert_rules.yml
groups:
  - name: trading_alerts
    rules:
      - alert: HighDailyLoss
        expr: daily_pnl < -0.02  # 2% daily loss
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High daily loss detected"
          description: "Daily P&L is below -2%: {{ $value }}"

      - alert: TWS_ConnectionDown
        expr: tws_connection_status == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "TWS connection is down"
          description: "Lost connection to TWS API"

      - alert: StrategyError
        expr: strategy_error_count > 5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Multiple strategy errors"
          description: "Strategy {{ $labels.strategy }} has {{ $value }} errors"

  - name: system_alerts
    rules:
      - alert: HighMemoryUsage
        expr: memory_usage_percent > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Memory usage is {{ $value }}%"

      - alert: DatabaseConnectionFailed
        expr: database_connection_status == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Database connection failed"
          description: "Cannot connect to PostgreSQL database"
```

### **Custom Metrics Collection**
```python
# monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time

# Trading metrics
trades_total = Counter('trades_total', 'Total number of trades', ['strategy', 'symbol', 'side'])
trade_pnl = Histogram('trade_pnl', 'Trade P&L distribution', ['strategy'])
portfolio_value = Gauge('portfolio_value', 'Current portfolio value')
daily_pnl = Gauge('daily_pnl', 'Daily profit/loss')
position_count = Gauge('position_count', 'Number of open positions')

# System metrics
api_requests = Counter('api_requests_total', 'Total API requests', ['endpoint', 'method', 'status'])
api_response_time = Histogram('api_response_seconds', 'API response time', ['endpoint'])
tws_connection_status = Gauge('tws_connection_status', 'TWS connection status (1=connected, 0=disconnected)')
strategy_status = Gauge('strategy_status', 'Strategy status', ['strategy_name'])

# Risk metrics
max_drawdown = Gauge('max_drawdown', 'Maximum drawdown')
sharpe_ratio = Gauge('sharpe_ratio', 'Portfolio Sharpe ratio')
position_concentration = Gauge('position_concentration', 'Largest position as % of portfolio')

class MetricsCollector:
    def __init__(self):
        # Start metrics server
        start_http_server(8001)
    
    def record_trade(self, strategy: str, symbol: str, side: str, pnl: float):
        trades_total.labels(strategy=strategy, symbol=symbol, side=side).inc()
        trade_pnl.labels(strategy=strategy).observe(pnl)
    
    def update_portfolio_metrics(self, value: float, daily_pnl_val: float, 
                                positions: int):
        portfolio_value.set(value)
        daily_pnl.set(daily_pnl_val)
        position_count.set(positions)
    
    def update_risk_metrics(self, drawdown: float, sharpe: float, 
                           concentration: float):
        max_drawdown.set(drawdown)
        sharpe_ratio.set(sharpe)
        position_concentration.set(concentration)
```

---

## 🔄 Backup & Disaster Recovery

### **Automated Backup Service**
```python
# scripts/backup_service.py
import os
import schedule
import time
import subprocess
from datetime import datetime, timedelta
import boto3
import logging

class BackupService:
    def __init__(self):
        self.db_url = os.getenv('DATABASE_URL')
        self.s3_bucket = os.getenv('BACKUP_S3_BUCKET')
        self.s3_client = boto3.client('s3')
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    def backup_database(self):
        """Create database backup"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_file = f"tws_robot_backup_{timestamp}.sql"
        
        try:
            # Create PostgreSQL dump
            subprocess.run([
                'pg_dump', 
                self.db_url, 
                '-f', f'/app/backups/{backup_file}'
            ], check=True)
            
            # Upload to S3
            self.s3_client.upload_file(
                f'/app/backups/{backup_file}',
                self.s3_bucket,
                f'database/{backup_file}'
            )
            
            # Clean up local file
            os.remove(f'/app/backups/{backup_file}')
            
            self.logger.info(f"Database backup completed: {backup_file}")
            
        except Exception as e:
            self.logger.error(f"Backup failed: {e}")
            self.send_alert(f"Database backup failed: {e}")
    
    def backup_configuration(self):
        """Backup configuration files"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        try:
            # Create tar archive of config directory
            subprocess.run([
                'tar', '-czf', f'/app/backups/config_{timestamp}.tar.gz',
                '/app/config'
            ], check=True)
            
            # Upload to S3
            self.s3_client.upload_file(
                f'/app/backups/config_{timestamp}.tar.gz',
                self.s3_bucket,
                f'config/config_{timestamp}.tar.gz'
            )
            
            # Clean up
            os.remove(f'/app/backups/config_{timestamp}.tar.gz')
            
            self.logger.info(f"Configuration backup completed")
            
        except Exception as e:
            self.logger.error(f"Config backup failed: {e}")
    
    def cleanup_old_backups(self):
        """Remove backups older than 30 days"""
        cutoff_date = datetime.now() - timedelta(days=30)
        
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix='database/'
            )
            
            for obj in response.get('Contents', []):
                obj_date = obj['LastModified'].replace(tzinfo=None)
                if obj_date < cutoff_date:
                    self.s3_client.delete_object(
                        Bucket=self.s3_bucket,
                        Key=obj['Key']
                    )
                    self.logger.info(f"Deleted old backup: {obj['Key']}")
        
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
    
    def send_alert(self, message: str):
        """Send backup failure alert"""
        # Implement Slack/email notification
        pass
    
    def start_scheduler(self):
        """Start backup scheduler"""
        # Daily database backup at 2 AM
        schedule.every().day.at("02:00").do(self.backup_database)
        
        # Weekly config backup on Sunday at 3 AM
        schedule.every().sunday.at("03:00").do(self.backup_configuration)
        
        # Daily cleanup at 4 AM
        schedule.every().day.at("04:00").do(self.cleanup_old_backups)
        
        self.logger.info("Backup scheduler started")
        
        while True:
            schedule.run_pending()
            time.sleep(60)

if __name__ == "__main__":
    backup_service = BackupService()
    backup_service.start_scheduler()
```

### **Disaster Recovery Procedures**
```bash
#!/bin/bash
# scripts/disaster_recovery.sh

# Disaster Recovery Script
# Usage: ./disaster_recovery.sh [backup_date]

BACKUP_DATE=${1:-"latest"}
S3_BUCKET=${BACKUP_S3_BUCKET}
POSTGRES_HOST=${DB_HOST}
POSTGRES_DB=${DB_NAME}
POSTGRES_USER=${DB_USER}

echo "Starting disaster recovery process..."

# 1. Download latest database backup from S3
echo "Downloading database backup..."
if [ "$BACKUP_DATE" = "latest" ]; then
    aws s3 cp s3://$S3_BUCKET/database/ ./recovery/ --recursive --exclude "*" --include "*.sql" | tail -1
    BACKUP_FILE=$(ls -t ./recovery/*.sql | head -1)
else
    aws s3 cp s3://$S3_BUCKET/database/tws_robot_backup_$BACKUP_DATE.sql ./recovery/
    BACKUP_FILE="./recovery/tws_robot_backup_$BACKUP_DATE.sql"
fi

# 2. Stop current services
echo "Stopping services..."
docker-compose down

# 3. Backup current database (just in case)
echo "Creating safety backup of current database..."
pg_dump postgresql://$POSTGRES_USER@$POSTGRES_HOST/$POSTGRES_DB > ./recovery/current_db_backup.sql

# 4. Restore from backup
echo "Restoring database from backup..."
dropdb --if-exists postgresql://$POSTGRES_USER@$POSTGRES_HOST/$POSTGRES_DB
createdb postgresql://$POSTGRES_USER@$POSTGRES_HOST/$POSTGRES_DB
psql postgresql://$POSTGRES_USER@$POSTGRES_HOST/$POSTGRES_DB < $BACKUP_FILE

# 5. Download and restore configuration
echo "Restoring configuration..."
aws s3 cp s3://$S3_BUCKET/config/ ./recovery/ --recursive
tar -xzf ./recovery/config_*.tar.gz -C ./

# 6. Restart services
echo "Restarting services..."
docker-compose up -d

# 7. Verify system health
echo "Verifying system health..."
sleep 30
curl -f http://localhost:8000/health || echo "WARNING: Health check failed"

echo "Disaster recovery completed!"
echo "Backup file used: $BACKUP_FILE"
echo "Please verify all systems are functioning correctly."
```

---

## 🚀 Deployment Scripts

### **Automated Deployment**
```bash
#!/bin/bash
# scripts/deploy.sh

set -e

ENVIRONMENT=${1:-"production"}
VERSION=${2:-"latest"}
DEPLOY_DIR="/opt/tws-robot"

echo "Deploying TWS Robot v$VERSION to $ENVIRONMENT..."

# 1. Pre-deployment checks
echo "Running pre-deployment checks..."
./scripts/pre_deploy_check.sh

# 2. Create deployment directory
sudo mkdir -p $DEPLOY_DIR
cd $DEPLOY_DIR

# 3. Download latest code
echo "Downloading application code..."
git clone https://github.com/your-org/tws-robot.git . || git pull

# 4. Build Docker images
echo "Building Docker images..."
docker-compose -f docker-compose.production.yml build

# 5. Run database migrations
echo "Running database migrations..."
docker-compose -f docker-compose.production.yml run --rm tws-robot python scripts/migrate.py

# 6. Start services with zero downtime
echo "Starting services..."
docker-compose -f docker-compose.production.yml up -d

# 7. Health checks
echo "Performing health checks..."
for i in {1..30}; do
    if curl -f http://localhost:8000/health > /dev/null 2>&1; then
        echo "Health check passed!"
        break
    fi
    echo "Waiting for services to start... ($i/30)"
    sleep 10
done

# 8. Run smoke tests
echo "Running smoke tests..."
python tests/smoke_tests.py

# 9. Send deployment notification
echo "Deployment completed successfully!"
curl -X POST -H 'Content-type: application/json' \
    --data "{\"text\":\"TWS Robot v$VERSION deployed to $ENVIRONMENT successfully!\"}" \
    $SLACK_WEBHOOK_URL

echo "Deployment of TWS Robot v$VERSION to $ENVIRONMENT completed!"
```

---

## 🛠️ Troubleshooting

### **Common Issues and Solutions**

#### **TWS Connection Issues**

**Problem:** Cannot connect to TWS API
```
Error: [Errno 10061] No connection could be made
```

**Solutions:**
1. Verify TWS is running and logged in
2. Check TWS API settings: Configure → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Set "Socket port" to 7497 (paper) or 7496 (live)
   - Check "Read-Only API" is unchecked
   - Trusted IP addresses includes 127.0.0.1
3. Verify port configuration matches `config_paper.py` or `config_live.py`
4. Check firewall settings allow localhost connections
5. Restart TWS and wait 30 seconds before connecting

---

#### **Database Connection Failures**

**Problem:** PostgreSQL connection refused
```
psycopg2.OperationalError: could not connect to server
```

**Solutions:**
1. Verify PostgreSQL container is running: `docker ps | grep postgres`
2. Check connection string in environment variables
3. Verify database exists: `docker exec -it tws-postgres psql -U tws_user -l`
4. Check PostgreSQL logs: `docker logs tws-postgres`
5. Restart database container: `docker-compose restart postgres`
6. Verify network connectivity: `docker network inspect tws-network`

---

#### **Memory Issues**

**Problem:** High memory usage or OOM errors
```
Warning: Memory usage at 95%
```

**Solutions:**
1. Check container resource limits in docker-compose.yml
2. Increase Docker memory allocation: Docker Desktop → Settings → Resources
3. Monitor memory usage: `docker stats tws-robot`
4. Review strategy complexity and data retention policies
5. Enable data cleanup: Set `MAX_HISTORY_DAYS` environment variable
6. Consider horizontal scaling for multiple strategies

---

#### **Order Execution Failures**

**Problem:** Orders not executing or getting rejected
```
Error: Order rejected - insufficient permissions
```

**Solutions:**
1. Verify IB account permissions for API trading
2. Check account has sufficient buying power
3. Verify market hours - orders may queue outside trading hours
4. Check order parameters meet IB requirements (lot sizes, prices)
5. Review IB account messages in TWS for specific rejection reasons
6. Enable paper trading mode for testing: Use `config_paper.py`
7. Check rate limiter settings - may be throttling orders

---

#### **Performance Issues**

**Problem:** Slow API responses or high latency
```
Warning: API response time > 5s
```

**Solutions:**
1. Check Redis cache is running: `docker ps | grep redis`
2. Verify network latency to IB servers
3. Review database query performance: Enable SQL logging
4. Check Prometheus metrics for bottlenecks: `http://localhost:9090`
5. Optimize strategy calculations - move heavy compute off critical path
6. Consider increasing connection pool size
7. Review rate limiter configuration

---

#### **Missing Market Data**

**Problem:** No market data received
```
Error: No market data subscription for AAPL
```

**Solutions:**
1. Verify IB account has market data subscriptions
2. Check TWS market data settings: Global Configuration → Market Data
3. Subscribe to required data in IB Account Management
4. Verify contract details are correct (symbol, exchange, currency)
5. Check for market data permissions errors in TWS messages
6. Use delayed/frozen data for testing if live data unavailable

---

#### **Deployment Failures**

**Problem:** Docker container won't start
```
Error: Container exits immediately
```

**Solutions:**
1. Check container logs: `docker logs tws-robot`
2. Verify environment variables are set correctly
3. Check volume mounts exist and have correct permissions
4. Review Dockerfile.production for syntax errors
5. Test image locally: `docker run -it tws-robot:latest bash`
6. Verify all required dependencies are installed
7. Check health check configuration isn't too aggressive

---

#### **Backup Failures**

**Problem:** Database backups not completing
```
Error: pg_dump failed - permission denied
```

**Solutions:**
1. Verify S3 credentials are correct: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
2. Check S3 bucket exists and has write permissions
3. Verify database user has backup privileges
4. Check disk space: `df -h`
5. Review backup service logs: `docker logs tws-backup`
6. Test manual backup: `pg_dump $DATABASE_URL -f test_backup.sql`
7. Verify backup schedule is correct

---

#### **Alert System Not Working**

**Problem:** Not receiving alerts
```
No Slack/email notifications received
```

**Solutions:**
1. Verify webhook URLs are correct in environment variables
2. Test webhook manually: `curl -X POST $SLACK_WEBHOOK_URL -d '{"text":"test"}'`
3. Check alert rules in `monitoring/alert_rules.yml`
4. Verify Prometheus is scraping metrics: `http://localhost:9090/targets`
5. Check alertmanager is running: `docker ps | grep alertmanager`
6. Review alertmanager config: `monitoring/alertmanager.yml`
7. Check alert firing status in Prometheus: `http://localhost:9090/alerts`

---

#### **Test Failures**

**Problem:** pytest tests failing after deployment
```
FAILED tests/test_connection.py::test_tws_connection
```

**Solutions:**
1. Verify all dependencies are installed: `pip install -r requirements.txt`
2. Check test database is configured correctly
3. Ensure TWS is running for integration tests
4. Review test configuration in `pytest.ini`
5. Run tests in verbose mode: `pytest -vv`
6. Check test fixtures are properly initialized
7. Verify test data exists: `tests/test_cache/`

---

### **Getting Help**

If issues persist:
1. Check project documentation: `README.md`, `TECHNICAL_SPECS.md`
2. Review relevant code modules for inline documentation
3. Check IB TWS API documentation: https://interactivebrokers.github.io
4. Review container logs for detailed error messages
5. Enable debug logging: Set `LOG_LEVEL=DEBUG` environment variable

---

This comprehensive deployment guide provides everything needed to run TWS Robot v2.0 in production with proper security, monitoring, backup, disaster recovery, and troubleshooting procedures.