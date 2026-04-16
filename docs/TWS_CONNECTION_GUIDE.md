# Connecting to IBKR Trader Workstation (TWS)

**Step-by-step guide to connect TWS Robot to your Interactive Brokers account.**

---

## 📚 Navigation

**You are here:** TWS Connection Guide — Set up and connect to Interactive Brokers
**Prerequisites:** [Getting Started](GETTING_STARTED_30MIN.md) — Install TWS Robot first
**Next steps:** [Local Deployment](LOCAL_DEPLOYMENT.md) — Paper trading validation
**Reference:** [Quick Reference](QUICK_REFERENCE.md) — Commands cheat sheet

---

## Overview

TWS Robot connects to Interactive Brokers through their **Trader Workstation (TWS)** or **IB Gateway** application. The connection uses a local socket (TCP) to send orders and receive market data. You configure the connection once, then use the web dashboard to connect and disconnect as needed.

```
┌──────────────┐    socket     ┌──────────────┐    internet    ┌──────────────┐
│  TWS Robot   │◄─────────────►│  TWS / IB    │◄──────────────►│  Interactive │
│  (your bot)  │  127.0.0.1    │  Gateway     │                │  Brokers     │
│              │  port 7497    │  (running on │                │  servers     │
│              │  or 7496      │  your PC)    │                │              │
└──────────────┘               └──────────────┘                └──────────────┘
```

**Key points:**
- TWS (or IB Gateway) must be running on your computer before TWS Robot can connect
- Paper trading uses port **7497**, live trading uses port **7496**
- No internet ports need to be opened — everything runs on `127.0.0.1` (localhost)

---

## Step 1: Install IBKR Trader Workstation

If you don't already have TWS installed:

1. Go to [Interactive Brokers TWS Download Page](https://www.interactivebrokers.com/en/trading/tws.php)
2. Download **TWS Latest** for your operating system (Windows, Mac, or Linux)
3. Run the installer and follow the prompts
4. Launch TWS after installation

> 💡 **Alternative:** You can also use **IB Gateway** instead of the full TWS application. IB Gateway is lighter weight (no trading UI) and is better suited for always-on automated trading. Download it from the same page. The API configuration steps below are the same for both.

### Create a Paper Trading Account (Recommended First Step)

If you don't have a paper trading account:

1. Log in to [IBKR Account Management](https://www.interactivebrokers.com/portal)
2. Navigate to **Settings → Account Settings → Paper Trading Account**
3. Click **Create** or **Reset** your paper trading account
4. Note your paper trading account ID (starts with `DU` followed by numbers, e.g., `DU1234567`)

---

## Step 2: Configure TWS API Settings

TWS needs to be configured to accept API connections from TWS Robot. **You only need to do this once.**

### Open API Settings

1. Launch TWS and log in (use your **paper trading** credentials to start)
2. In the TWS menu bar, click **Edit** (Windows/Linux) or **TWS** (Mac)
3. Select **Global Configuration...**
4. In the left sidebar, expand **API** and click **Settings**

### Enable API Access

Configure these settings:

| Setting | Value | Why |
|---------|-------|-----|
| **Enable ActiveX and Socket Clients** | ☑ Checked | Allows TWS Robot to connect via socket |
| **Socket port** | `7497` (paper) or `7496` (live) | The port TWS Robot connects to |
| **Allow connections from localhost only** | ☑ Checked (recommended) | Security: only your computer can connect |
| **Read-Only API** | ☐ Unchecked | TWS Robot needs to place orders |
| **Download open orders on connection** | ☑ Checked (recommended) | Keeps TWS Robot in sync with existing orders |
| **Send instrument-specific attributes for dual-mode API client in i...** | ☑ Checked (recommended) | Better API compatibility |

### Add Trusted IP Address

Still in the API Settings:

1. In the **Trusted IPs** section, click **Add**
2. Enter `127.0.0.1`
3. Click **OK**

> ⚠️ **Important:** If you don't add `127.0.0.1` to trusted IPs, TWS will show a confirmation dialog every time TWS Robot tries to connect. Adding the trusted IP allows automatic connections.

### Apply and Confirm

1. Click **Apply** then **OK** to save the settings
2. TWS may prompt you to restart — if so, restart TWS

### Verify the Port

After configuring, verify the correct port is active:

- **Paper trading login** → port should be **7497**
- **Live trading login** → port should be **7496**

> 💡 **Tip:** You can check which port TWS is listening on by looking at the bottom status bar in TWS. It typically shows the API port number.

---

## Step 3: Configure TWS Robot

### Set Up Your Environment File

1. In your `tws_robot` project directory, copy the example configuration:

```bash
cp .env.example .env
```

2. Open `.env` in a text editor and fill in your details:

```env
# Which environment to use by default: 'paper' or 'live'
TRADING_ENV=paper

# Paper Trading Configuration
PAPER_HOST=127.0.0.1
PAPER_PORT=7497
PAPER_CLIENT_ID=0
PAPER_ACCOUNT=DU1234567        # ← Replace with YOUR paper account ID

# Live Trading Configuration (set up later)
LIVE_HOST=127.0.0.1
LIVE_PORT=7496
LIVE_CLIENT_ID=1
LIVE_ACCOUNT=YOUR_LIVE_ACCOUNT_ID   # ← Replace when ready for live trading

LOG_LEVEL=INFO
```

**Where to find your account IDs:**
- **Paper account ID:** Shown in the TWS title bar when logged into paper trading (e.g., `DU1234567`)
- **Live account ID:** Shown in the TWS title bar when logged into live trading (e.g., `U1234567`)
- Also visible in **IBKR Account Management** → **Settings → Account Settings**

**Optional: Enable AI Features** (for strategy analysis and recommendations):
- Add your OpenAI API key to `.env`: `OPENAI_API_KEY=sk-...`
- AI features auto-enable when the key is present
- See [API Reference - AIClient](API_REFERENCE.md#aiclient---openai-integration) for details

> ⚠️ **Never commit your `.env` file to version control.** It's already in `.gitignore`.

---

## Step 4: Connect Using the Web Dashboard (Recommended)

The web dashboard is the easiest way to connect TWS Robot to your IBKR account.

### Launch the Dashboard

```bash
# Make sure your virtual environment is activated
source venv/bin/activate       # Mac/Linux
.\venv\Scripts\Activate.ps1    # Windows PowerShell

# Start the web dashboard
python scripts/run_web.py
```

Open your browser to **http://127.0.0.1:5000**.

### Navigate to the Settings Page

1. Click **Settings** in the navigation bar (or go to http://127.0.0.1:5000/settings)
2. You'll see the **TWS Connection** section at the top of the page

### Test the Connection First

Before connecting, verify TWS is reachable:

1. In the **Test Connection** area, you'll see host (`127.0.0.1`) and port (`7497`) fields
2. Make sure the port matches your TWS configuration (7497 for paper, 7496 for live)
3. Click **Test**
4. You should see **✅ Reachable** — this confirms TWS is running and the port is correct

If you see **❌ Not reachable**, check:
- Is TWS/IB Gateway running?
- Are you logged in to TWS?
- Does the port number match? (7497 for paper, 7496 for live)
- Did you enable "Enable ActiveX and Socket Clients" in TWS API settings?

### Connect to TWS

1. Click **Connect Paper** to connect to your paper trading account
2. The page will reload and the status should change from **Disconnected** to **Connected — PAPER**
3. The top status bar across the dashboard will also show the connection status

> 🔒 **Live trading:** Click **Connect Live** only after completing a 30-day paper trading validation. See [Local Deployment Guide](LOCAL_DEPLOYMENT.md) for the validation process.

### Disconnect

To disconnect from TWS:
1. Go to the **Settings** page
2. Click **Disconnect**
3. The status will change back to **Disconnected**

---

## Step 5: Connect Using the Command Line (Alternative)

If you prefer working in a terminal instead of the web dashboard:

### Test Connection

```bash
# Quick socket test — checks if TWS is reachable
python scripts/quick_connection_test.py

# Detailed connection diagnostics
python scripts/connection_test.py
```

### Connect and Trade

```bash
# Paper trading (default)
python tws_client.py --env paper

# Show current configuration
python tws_client.py --show-config

# Check account status and positions
python scripts/check_account.py          # Paper account (default)
python scripts/check_account.py paper    # Paper account
python scripts/check_account.py live     # Live account
```

---

## Step 6: Verify Everything Works

After connecting (via web dashboard or command line), verify the connection is healthy:

### From the Web Dashboard

1. **Top Status Bar** — should show "Connected" with your environment (PAPER or LIVE)
2. **Dashboard Page** — should show equity, daily P&L, and account information
3. **Settings Page** — TWS Connection status shows "Connected — PAPER" (or LIVE)

### From the Command Line

```bash
# Check account status (should show account details and positions)
python scripts/check_account.py

# Check market status
python scripts/market_status.py
```

### What Happens Under the Hood

When you click "Connect Paper" or run the connect command, TWS Robot:

1. **Loads configuration** from your `.env` file (host, port, account ID)
2. **Opens a socket connection** to TWS at `127.0.0.1:7497` (or 7496 for live)
3. **Waits for TWS handshake** — TWS sends a `connectAck` callback
4. **Receives a valid order ID** — TWS sends `nextValidId`, confirming the connection is fully ready
5. **Connection is established** — TWS Robot can now request data and place orders

Both callbacks (`connectAck` and `nextValidId`) must succeed within 10 seconds, or the connection times out.

---

## Troubleshooting

### "Connection failed" or "Not reachable"

| Check | How to Fix |
|-------|-----------|
| TWS is not running | Launch TWS and log in to your account |
| Wrong port | Paper trading = 7497, live trading = 7496. Check TWS API settings and your `.env` file |
| API not enabled | In TWS: Edit → Global Configuration → API → Settings → Enable "Enable ActiveX and Socket Clients" |
| Trusted IP missing | In TWS API Settings, add `127.0.0.1` to trusted IPs |
| TWS logged out | TWS may auto-logout after inactivity. Log back in |
| Wrong account type | Make sure you're logged into paper account for paper trading, live for live trading |

### "Connection timeout"

The connection times out after 10 seconds. Common causes:
- TWS is still loading (wait for TWS to fully start before connecting)
- Another application is using the same client ID (change `PAPER_CLIENT_ID` in `.env`)
- TWS is in "Restart" or maintenance mode (wait and try again)

### "Client ID already in use"

Each TWS connection needs a unique client ID. If you see this error:
1. Close any other applications connected to TWS
2. Or change `PAPER_CLIENT_ID` in your `.env` file to a different number (e.g., `10`)

### Connection Drops Unexpectedly

TWS Robot has automatic reconnection for common disconnections:
- **Error 1100:** TWS connectivity lost — auto-reconnects with exponential backoff
- **Error 502/503/504:** Connection errors — auto-reconnects up to 3 times
- **Error 1101/1102:** TWS connectivity restored — auto-reconnects

If the connection keeps dropping:
1. Check your internet connection
2. Ensure TWS is not set to auto-logout
3. Check TWS → Edit → Global Configuration → Lock and Exit → set auto-logoff time appropriately
4. Consider using **IB Gateway** instead of TWS for more stable automated connections

### TWS Shows Confirmation Dialog on Every Connection

This happens when `127.0.0.1` is not in the trusted IPs list:
1. In TWS: Edit → Global Configuration → API → Settings
2. Under **Trusted IPs**, add `127.0.0.1`
3. Click **Apply** then **OK**

---

## Quick Reference

### Ports

| Environment | Default Port | Config Variable |
|-------------|-------------|-----------------|
| Paper Trading | 7497 | `PAPER_PORT` |
| Live Trading | 7496 | `LIVE_PORT` |

### Connection Methods

| Method | Command |
|--------|---------|
| Web Dashboard | Go to Settings → Click "Connect Paper" or "Connect Live" |
| Command Line | `python tws_client.py --env paper` |
| Test Connection | Settings → Test button, or `python scripts/quick_connection_test.py` |
| Check Account | Dashboard page, or `python scripts/check_account.py` |

### TWS API Settings Checklist

- [ ] TWS or IB Gateway installed and running
- [ ] Logged in to the correct account (paper or live)
- [ ] Edit → Global Configuration → API → Settings opened
- [ ] "Enable ActiveX and Socket Clients" checked
- [ ] Socket port set to 7497 (paper) or 7496 (live)
- [ ] `127.0.0.1` added to trusted IPs
- [ ] "Read-Only API" unchecked
- [ ] `.env` file configured with correct account ID and port

---

## What's Next?

- **Run your first backtest:** [Getting Started (30 min)](GETTING_STARTED_30MIN.md) — no TWS connection needed
- **Start paper trading:** [Local Deployment](LOCAL_DEPLOYMENT.md) — 30-day validation process
- **Learn strategies:** [User Guide](USER_GUIDE.md) — understand what each strategy does
- **Go live safely:** [Live Trading Safety](LIVE_TRADING_SAFETY.md) — critical safety guide

---

**Need help?** Check the [Troubleshooting](#troubleshooting) section above, or see the [Debugging Guide](runbooks/debugging-strategies.md) for more detailed diagnostics.
