# TWS Robot - Interactive Brokers Trading Bot

A sophisticated automated trading system for Interactive Brokers using Python and the TWS API.

## Features

🔧 **Environment-Based Configuration**
- Supports both paper trading and live trading environments
- Configuration via `.env` files for security
- Easy switching between environments

📊 **Market Status Integration**
- Real-time US stock market status checking
- Automatic warnings for after-hours trading
- Safety prompts for live trading during market closures

🛡️ **Safety Features**
- Graceful connection handling with timeout support
- Comprehensive error handling and logging
- Protected sensitive data (account IDs masked)
- Confirmation prompts for live trading

⚡ **TWS Integration**
- Real-time market data streaming
- Historical data collection
- Account balance and portfolio monitoring
- Order execution capabilities

## Quick Start

### Prerequisites

1. **Interactive Brokers Account**: Paper trading or live account
2. **TWS or IB Gateway**: Must be running and configured
3. **Python 3.8+**: With pip package manager

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/evanlow/tws_robot.git
   cd tws_robot
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv .
   ```

3. **Activate virtual environment**:
   ```bash
   # Windows
   .\Scripts\Activate.ps1
   
   # macOS/Linux  
   source bin/activate
   ```

4. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

5. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env with your account details
   ```

### Configuration

Edit the `.env` file with your Interactive Brokers configuration:

```env
# Trading Environment: 'paper' or 'live'
TRADING_ENV=paper

# Paper Trading Configuration
PAPER_HOST=127.0.0.1
PAPER_PORT=7497
PAPER_CLIENT_ID=0
PAPER_ACCOUNT=DU2746208

# Live Trading Configuration
LIVE_HOST=127.0.0.1
LIVE_PORT=7496
LIVE_CLIENT_ID=1
LIVE_ACCOUNT=YOUR_LIVE_ACCOUNT_ID
```

## Usage

### Basic Usage

```bash
# Paper trading (default)
python tws_client.py --timeout 30

# Live trading  
python tws_client.py --env live --timeout 60

# Show current configuration
python tws_client.py --show-config

# Skip market status check
python tws_client.py --skip-market-check
```

### Command Line Options

| Option | Description |
|--------|-------------|
| `--timeout, -t` | Set timeout in seconds (default: no timeout) |
| `--env, -e` | Trading environment: `paper` or `live` |
| `--show-config` | Display current configuration and exit |
| `--skip-market-check` | Skip market status verification |
| `--no-timeout` | Run without timeout |
| `--help, -h` | Show help message |

### Market Status Check

```bash
# Check current US market status
python market_status.py
```

## Project Structure

```
tws_robot/
├── .env.example          # Configuration template
├── .env                  # Your configuration (not in git)
├── .gitignore           # Git ignore rules
├── requirements.txt     # Python dependencies
├── env_config.py        # Environment configuration loader
├── market_status.py     # US market status checker
├── tws_client.py        # Main TWS client application
├── trading_bot_template.py  # Trading strategy template
├── config_paper.py      # Legacy paper config (deprecated)
├── config_live.py       # Legacy live config (deprecated)
├── test_input.py        # Input handling tests
└── ibapi/              # Interactive Brokers API library
```

## Safety & Security

⚠️ **Important Security Notes**:

- **Never commit `.env` file** - Contains sensitive account information
- **Use paper trading first** - Test strategies before going live
- **Monitor live trades** - Always supervise automated trading
- **Market hours awareness** - System warns about after-hours trading

## TWS Setup

1. **Start TWS or IB Gateway**
2. **Enable API connections**:
   - File → Global Configuration → API → Settings
   - Enable "Enable ActiveX and Socket Clients"
   - Set Socket Port: 7497 (paper) or 7496 (live)
3. **Add trusted IPs**: Add `127.0.0.1` if needed

## Error Codes

Common TWS error codes you might see:

- **2104**: Market data farm connection OK (informational)
- **2106**: HMDS data farm connection OK (informational)  
- **2158**: Security definition data farm connection OK (informational)
- **2108**: Unable to subscribe to market data (normal during off-hours)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is for educational purposes only. Please ensure you understand the risks of automated trading and comply with all applicable regulations.

## Disclaimer

**⚠️ Trading Risk Warning**: 
- Automated trading involves substantial risk of loss
- Past performance does not guarantee future results
- Only trade with money you can afford to lose
- Always test strategies in paper trading first
- Monitor your automated systems at all times

The authors are not responsible for any financial losses incurred through the use of this software.

## Support

For questions or issues:
1. Check existing [Issues](https://github.com/evanlow/tws_robot/issues)
2. Create a new issue if needed
3. Include relevant logs and configuration details

---

**Happy Trading! 📈**