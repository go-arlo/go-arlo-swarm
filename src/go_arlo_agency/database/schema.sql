CREATE TABLE IF NOT EXISTS tokens (
    id SERIAL PRIMARY KEY,
    contract_address TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    chain TEXT DEFAULT 'solana',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    analysis_exists BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS analyses (
    id SERIAL PRIMARY KEY,
    contract_address TEXT UNIQUE NOT NULL,
    token_ticker TEXT NOT NULL,
    chain TEXT NOT NULL,
    final_score NUMERIC NOT NULL,
    token_safety JSONB NOT NULL,
    market_position JSONB NOT NULL,
    social_sentiment JSONB NOT NULL,
    holder_analysis JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contract_address) REFERENCES tokens(contract_address)
);

DO $$ 
BEGIN 
    IF NOT EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name='analyses' AND column_name='updated_at'
    ) THEN
        ALTER TABLE analyses 
        ADD COLUMN updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
        
        -- Update existing rows to have updated_at match created_at
        UPDATE analyses 
        SET updated_at = created_at 
        WHERE updated_at IS NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_token_address ON tokens(contract_address);
CREATE INDEX IF NOT EXISTS idx_analysis_address ON analyses(contract_address); 
