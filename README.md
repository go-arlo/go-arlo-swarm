# Go Arlo Agents

A powerful token analysis platform that combines multiple AI agents to provide comprehensive token analysis, market insights, and social sentiment analysis.

## Prerequisites

- Python 3.11+
- PostgreSQL 12+
- API keys (see below)

## Required API Keys

You'll need the following API keys to run the application:

1. **OpenAI API Key**
   - Required for the AI agents
   - Get it from: https://platform.openai.com/api-keys

2. **Moralis API Key**
   - Required for blockchain data and transaction analysis
   - Get it from: https://admin.moralis.io/web3apis

3. **Birdeye API Key**
   - Required for market data and token information
   - Get it from: https://birdeye.so/developers

4. **LunarCrush API Key**
   - Required for social sentiment analysis
   - Get it from: https://lunarcrush.com/developers

5. **TweetScout API Key**
   - Required for Twitter analysis
   - Get it from: https://tweetscout.io

6. **Twitter API Keys**
   - Required for posting analysis replies on Twitter
   - Get them from: https://developer.twitter.com/en/portal/dashboard
   - You'll need:
     - API Key (Consumer Key)
     - API Key Secret (Consumer Secret)
     - Access Token
     - Access Token Secret

7. **Telegram Bot Token**
   - Required for Telegram integration
   - Get it from: @BotFather on Telegram

## Local Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/go-arlo/go-arlo-agents.git
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r src/requirements.txt
   ```

4. **Set up environment variables**
   ```bash
   # Copy the example environment file
   cp src/example.env src/.env
   
   # Edit the .env file with your actual API keys
   nano src/.env  # or use your preferred text editor
   ```
   
   The `.env` file contains all the necessary environment variables. Make sure to:
   - Replace all placeholder values with your actual API keys
   - Generate a secure random string for `APP_TOKEN`
   - Update the `PUBLIC_URL` with your actual deployment URL
   - Configure the PostgreSQL connection details

5. **Set up PostgreSQL database**
   Create a new PostgreSQL database and update the database connection variables in your `.env` file:
   ```
   PGHOST=your_db_host
   PGPORT=5432
   PGUSER=your_db_user
   PGPASSWORD=your_db_password
   PGDATABASE=your_db_name
   ```

6. **Initialize the database**
   ```bash
   python src/go_arlo_agency/database/init_db.py
   ```

7. **Run database migrations**
   ```bash
   python src/go_arlo_agency/database/migrations.py
   ```

## Running the Application

1. **Start the FastAPI server**
   ```bash
   cd src
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

2. **Set up Telegram webhook**
   ```bash
   python set_webhook.py
   ```

## Using the Agents

The application provides several ways to interact with the agents:

1. **API Endpoints**
   - `/api/analyze` - Analyze a token
   - `/api/analysis/{contract_address}` - Get analysis results
   - `/api/tokens` - List all analyzed tokens
   - `/api/trending` - Get trending tokens

2. **Telegram Bot**
   - Mention the bot in a message with a token address or symbol
   - The bot will analyze the token and reply with results

3. **Twitter Integration**
   - Reply to tweets with token addresses
   - The bot will analyze and reply with results
   - Make sure your Twitter API keys have write permissions

## Development

- The main agent logic is in `src/go_arlo_agency/agency.py`
- Database operations are in `src/go_arlo_agency/database/`
- API endpoints are in `src/main.py`
- Agent tools for each agent are in `src/go_arlo_agency/*/tools/`

## License

This project is licensed under the MIT License - see the LICENSE file for details.
