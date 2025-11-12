# Go Arlo Swarm

A powerful risk management tool that combines multiple AI agents to transform comprehensive token analysis, market insights, and social sentiment input into cohesive narratives.

## Setup

1. **Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables** (copy from `.env.example`):
   ```bash
   # Required
   OPENAI_API_KEY=your_openai_api_key_here
   XAI_API_KEY=your_xai_api_key_here

   TWEET_SCOUT_ID=your_tweetscout_api_key_here
   MORALIS_API_KEY=your_moralis_api_key_here
   BIRDEYE_API_KEY=your_birdeye_api_key_here
   ```

3. **External APIs Used**:
   - **BirdEye**: Market data and token safety
   - **Moralis**: Holder statistics
   - **TweetScout**: Social media sentiment data
   - **X.AI (Grok)**: AI-powered analysis and narrative generation

## Usage

```bash
python main.py --address 0x1234... --chain ethereum --symbol ETH

# Supported chain options: solana, ethereum, base, bsc, shibarium
```

### Testing
```bash
# Test with sample tokens
python test_agency.py --samples

# Test specific token
python test_agency.py --address So11111111111111111111111111111111111111112 --symbol SOL
```

## Supported Chains

- Solana (`solana`)
- Ethereum (`ethereum`)
- Base (`base`)
- BNB Smart Chain (`bsc`)

## Output

The system generates four structured narrative sections:

1. **Market Overview** (max 500 chars): Price action, valuation, volume/liquidity analysis
2. **Holder Insights** (max 500 chars): Distribution patterns and concentration analysis
3. **Safety Notes** (max 500 chars): Risk assessment based on available metrics
4. **Social & Trends** (max 500 chars): Sentiment classification and trending topics

## Files Structure

- `main.py`: Entry point and CLI interface
- `data_fetchers.py`: External API integration (GeckoTerminal, Moralis)
- `agency.py`: Agent system configuration
- `grok_sentiment_agent/`: Social sentiment analysis agent
- `grok_narration_agent/`: Narrative generation agent
- `test_agency.py`: Testing and validation script
