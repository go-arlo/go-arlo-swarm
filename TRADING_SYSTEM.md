# Comprehensive Trading System

A complete automated trading solution with token discovery, AI-powered scam detection, analysis, buying, and intelligent auto-selling capabilities.

## Overview

The Comprehensive Trading System combines all trading functionality into a single, unified system that can:
- **Discover** trending tokens using various filter strategies
- **Analyze** tokens using structured data with configurable risk profiles
- **Detect Scams** using Grok AI to analyze social media sentiment
- **Buy** promising tokens with intelligent position sizing
- **Sell** automatically based on PnL thresholds and profit-taking strategies

## Quick Start

### CLI Usage

#### Basic Usage (Dry Run)
```bash
cd src && python3 trading_system.py
```

#### Live Trading with Auto-Sell
```bash
cd src && python3 trading_system.py --live --auto-sell --cycles 999
```

### API Usage

#### Start Trading System (Dry Run)
```bash
curl -X POST http://localhost:8000/trading/system/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-app-token" \
  -d '{}'
```

#### Start Live Trading with Auto-Sell
```bash
curl -X POST http://localhost:8000/trading/system/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your-app-token" \
  -d '{
    "live_trading": true,
    "enable_auto_sell": true,
    "cycles": 999,
    "interval_minutes": 3
  }'
```

#### Stop Trading System
```bash
curl -X POST http://localhost:8000/trading/system/stop \
  -H "X-API-Key: your-app-token"
```

#### Check Status
```bash
curl http://localhost:8000/trading/system/status
```

## Command Line Options

### Trading Mode
- `--live` - Enable LIVE trading with real money (default: dry run)
- `--risk {strict,conservative,moderate,aggressive}` - Risk profile (default: strict)
- `--max-amount N` - Maximum amount in SOL per trade (e.g., 0.01)

### Cycle Control
- `--cycles N` - Number of cycles to run (999 for continuous, default: 1)
- `--interval N` - Minutes between cycles (default: 3)

### Auto-Sell Configuration
- `--auto-sell` - Enable automatic selling based on PnL
- `--test-sell` - Test sell strategy on current holdings (no execution)
- `--sell-interval N` - Seconds between sell checks (default: 60)
- `--loss-threshold N` - Stop loss percentage (default: -10.0)
- `--profit-tiers "30:30,100:30,200:25,900:15"` - Custom profit tiers

## API Endpoints

### System Management (Require API Key)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/trading/system/start` | Start the trading system |
| POST | `/trading/system/stop` | Stop the trading system |
| GET | `/trading/system/status` | Get current status |
| GET | `/trading/system/filter-presets` | List token filter presets |
| GET | `/trading/system/risk-profiles` | List risk profiles |

### Start Request Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `live_trading` | bool | `false` | Enable real trading |
| `cycles` | int | `1` | Number of cycles (999 = continuous) |
| `interval_minutes` | int | `3` | Minutes between cycles |
| `risk_profile` | string | `"strict"` | Risk profile to use |
| `enable_auto_sell` | bool | `false` | Enable auto-selling |
| `sell_check_interval` | int | `30` | Seconds between sell checks |
| `loss_threshold` | float | `-10.0` | Stop loss percentage |
| `profit_tiers` | array | null | Custom profit tiers |
| `max_trade_amount` | float | null | Max SOL per trade |
| `filter_preset` | string | `"optimized_default"` | Token filter preset |

### Trading Analysis (Require API Key for execution)

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| POST | `/trading/analyze` | No | Analyze token |
| POST | `/trading/auto-execute` | Yes | Analyze + execute trade |
| POST | `/trading/execute` | Yes | Execute Jupiter swap |
| POST | `/trading/quote` | No | Get swap quote |
| GET | `/trading/criteria` | No | Get current criteria |
| PUT | `/trading/criteria` | No | Update criteria |
| POST | `/trading/criteria/presets/{preset}` | No | Set preset |
| GET | `/trading/presets` | No | List presets |
| GET | `/trading/health` | No | System health |
| GET | `/trading/rejections` | No | List rejected tokens |
| GET | `/trading/rejections/stats` | No | Rejection statistics |

### Authentication

Protected endpoints require the `X-API-Key` header:
```bash
curl -X POST http://localhost:8000/trading/system/start \
  -H "X-API-Key: your-app-token" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## Risk Profiles

### Strict (Default - Recommended)
All criteria must pass for a BUY decision:
- Token Safety: LOW risk only
- Holder Concentration: Up to HIGH (35%)
- Market Pressure: NEUTRAL or BUY
- TweetScout Score: 200+
- **Grok Sentiment: Positive or Neutral**
- **Scam Risk: Unlikely or Uncertain**

### Conservative
Most restrictive settings:
- Token Safety: LOW risk only
- Holder Concentration: LOW only (10%)
- Market Pressure: BUY only
- TweetScout Score: 500+
- **Grok Sentiment: Positive only**
- **Scam Risk: Unlikely only**
- Min Liquidity: $100,000
- Min Holders: 500

### Moderate
Balanced risk/reward:
- Token Safety: LOW risk only
- Holder Concentration: Up to HIGH (35%)
- Market Pressure: NEUTRAL or BUY
- TweetScout Score: 200+
- **Grok Sentiment: Positive or Neutral**
- **Scam Risk: Unlikely or Uncertain**

### Aggressive
Higher risk tolerance:
- Token Safety: Up to HIGH risk
- Holder Concentration: Up to VERY_HIGH (50%+)
- Market Pressure: Any (including SELL)
- TweetScout Score: 200+
- **Grok Sentiment: Any (Positive, Neutral, or Negative)**
- **Scam Risk: Unlikely or Uncertain (still blocks Likely scams)**

## AI-Powered Scam Detection

The system uses **Grok AI** with X/Twitter search to analyze token sentiment:

### How It Works
1. Searches recent X posts about the token
2. Analyzes tone, credibility, and red flags
3. Detects coordinated shilling, bot activity, rug warnings
4. Returns structured assessment

### Sentiment Ratings
| Rating | Icon | Meaning |
|--------|------|---------|
| Positive | Green | Genuine excitement |
| Neutral | Yellow | Mixed or limited discussion |
| Negative | Red | Warnings or concerns |

### Scam Risk Assessment
| Rating | Icon | Meaning |
|--------|------|---------|
| Unlikely | Green Check | No major red flags |
| Uncertain | Orange Diamond | Some concerns, proceed with caution |
| Likely | Red Alert | Strong scam indicators - **BLOCKED** |

## Auto-Sell Strategy

### Default Profit Tiers
| Profit | Multiplier | Sell % | Description |
|--------|------------|--------|-------------|
| +30% | 1.3x | 30% | Initial profit taking |
| +100% | 2x | 30% | Major profit realization |
| +200% | 3x | 25% | Additional profit capture |
| +900% | 10x | 15% | Final profit taking |

### Stop Loss
- Default: **-10%** (configurable with `--loss-threshold`)
- Sells 100% of position to minimize losses

### Custom Profit Tiers
Format: `"profit1:sell1,profit2:sell2,..."`

Example: `--profit-tiers "25:30,50:30,100:30,300:10"`
- At +25% profit: sell 30%
- At +50% profit: sell 30%
- At +100% profit: sell 30%
- At +300% profit: sell 10%

## Token Filter Presets

| Preset | Description |
|--------|-------------|
| `optimized_default` | 30min-72h age, $50k liq, $75k 1h vol |
| `daily_driver` | Consistent opportunities, $50k liq |
| `high_momentum` | Aggressive plays, high volume change |
| `volume_liquidity_balanced` | 1.5x-6x vol/liq ratio |
| `high_liquidity_trending` | High liq with volume increase |
| `new_listings` | Last 24 hours |
| `recent_listings_72h` | Last 72 hours |

## Environment Configuration

Required variables in `.env`:

```bash
# Authentication (Required for API)
APP_TOKEN=your-secret-api-token

# Public URL
PUBLIC_URL=https://your-app.up

# Wallet Configuration
DELEGATED_WALLET_ADDRESS=your_wallet_address

# Trading Keys (for live trading)
TURNKEY_ORGANIZATION_ID=your_org_id
TURNKEY_API_PUBLIC_KEY=your_public_key
TURNKEY_API_PRIVATE_KEY=your_private_key

# API Keys
BIRDEYE_API_KEY=your_birdeye_key
TWEET_SCOUT_ID=your_tweetscout_key
XAI_API_KEY=your_xai_key  # For Grok sentiment analysis

# Database (Railway PostgreSQL)
DATABASE_PUBLIC_URL=postgresql://user:pass@host:port/db

# Optional
MAX_AMOUNT=0.1  # Max SOL per trade
```

## Data Storage

- **Rejections**: PostgreSQL `rejected_tokens` table (TTL: 7 days)
- **Positions**: Tracked in memory during session

## Trading Criteria Checks

The system evaluates tokens using structured data:

| Check | Source | What It Checks |
|-------|--------|----------------|
| Token Safety | BirdEye | Contract risks, honeypot detection |
| Holder Concentration | Moralis | Top 10 holder percentage |
| Bundler Risk | Custom | Launch pattern detection (Solana) |
| Market Pressure | BirdEye | 24h buy/sell pressure |
| TweetScout Score | TweetScout | Social credibility score |
| Grok Sentiment | xAI/Grok | AI sentiment analysis |
| Scam Assessment | xAI/Grok | Scam likelihood detection |

## Usage Examples

### CLI Examples

```bash
# Conservative dry run
python3 trading_system.py --risk conservative --cycles 5

# Live trading with strict mode (default)
python3 trading_system.py --live --cycles 999

# Small position live trading
python3 trading_system.py --live --max-amount 0.01 --cycles 999

# Full auto-trading with custom sell strategy
python3 trading_system.py --live --auto-sell \
  --loss-threshold -15 \
  --profit-tiers "25:25,50:25,100:25,200:25" \
  --cycles 999

# Test sell strategy on current holdings
python3 trading_system.py --test-sell

# Execute test sell strategy (real sells!)
python3 trading_system.py --test-sell --live
```

### API Examples

```bash
# Start with all defaults (dry run, 1 cycle)
curl -X POST http://localhost:8000/trading/system/start \
  -H "X-API-Key: your-token" \
  -H "Content-Type: application/json" \
  -d '{}'

# Start continuous live trading
curl -X POST http://localhost:8000/trading/system/start \
  -H "X-API-Key: your-token" \
  -H "Content-Type: application/json" \
  -d '{
    "live_trading": true,
    "cycles": 999,
    "interval_minutes": 5,
    "enable_auto_sell": true,
    "risk_profile": "strict"
  }'

# Check status
curl http://localhost:8000/trading/system/status

# Get available presets
curl http://localhost:8000/trading/system/filter-presets
curl http://localhost:8000/trading/system/risk-profiles

# Stop system
curl -X POST http://localhost:8000/trading/system/stop \
  -H "X-API-Key: your-token"

# Analyze a specific token
curl -X POST http://localhost:8000/trading/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "token_address": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
    "chain": "solana"
  }'
```

## Safety Features

### Built-in Protections
- **Dry run mode** by default
- **Strict mode** requires ALL criteria to pass
- **Grok AI** detects scams before buying
- **Rejection tracking** prevents re-analyzing bad tokens (stored in PostgreSQL)
- **Position limits** via MAX_AMOUNT
- **API authentication** protects sensitive endpoints
- **Graceful shutdown** with Ctrl+C or /system/stop

### What Gets Blocked
- Tokens with "Likely" scam assessment
- Tokens with negative sentiment (in strict/conservative mode)
- Tokens failing safety analysis
- Tokens with high holder concentration
- Previously rejected tokens (for 7 days)

## Troubleshooting

### Common Issues
- **APP_TOKEN not configured**: Set `APP_TOKEN` in `.env`
- **401 Unauthorized**: Include `X-API-Key` header
- **Database error**: Check `DATABASE_PUBLIC_URL` is set correctly
- **Grok analysis failed**: Check `XAI_API_KEY` is valid
- **No wallet address**: Set `DELEGATED_WALLET_ADDRESS`

### Debug Mode
The trading analyzer runs with `debug=True` by default, showing detailed criteria evaluation in logs.
