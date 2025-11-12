#!/bin/bash

# Test runner script for fetch_all_token_data
# This script sets up the environment and runs the test

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🧪 Go-Arlo Token Data Fetcher Test Runner${NC}"
echo -e "${BLUE}=========================================${NC}"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")"

# Check if we're in the right directory
if [[ ! -f "$SRC_DIR/data_fetchers.py" ]]; then
    echo -e "${RED}❌ Error: data_fetchers.py not found in $SRC_DIR${NC}"
    echo "Please run this script from the go-arlo-swarm/src/tests directory"
    exit 1
fi

# Check for virtual environment
if [[ -f "$SRC_DIR/../venv_linux/bin/python" ]]; then
    PYTHON_CMD="$SRC_DIR/../venv_linux/bin/python"
    echo -e "${GREEN}✅ Using venv_linux Python: $PYTHON_CMD${NC}"
elif [[ -f "$SRC_DIR/../venv/bin/python" ]]; then
    PYTHON_CMD="$SRC_DIR/../venv/bin/python"
    echo -e "${GREEN}✅ Using venv Python: $PYTHON_CMD${NC}"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    echo -e "${YELLOW}⚠️  Using system Python3: $PYTHON_CMD${NC}"
else
    echo -e "${RED}❌ No Python found${NC}"
    exit 1
fi

# Check for .env file
if [[ ! -f "$SRC_DIR/.env" ]]; then
    echo -e "${YELLOW}⚠️  No .env file found at $SRC_DIR/.env${NC}"
    echo "Make sure you have BIRDEYE_API_KEY and optionally MORALIS_API_KEY set"
fi

# Function to run test
run_test() {
    local token_address="$1"
    local chain="$2"

    echo -e "\n${BLUE}🚀 Testing token: $token_address on $chain${NC}"
    echo -e "${BLUE}================================================${NC}"

    cd "$SRC_DIR"
    $PYTHON_CMD tests/test_fetch_all_token_data.py "$token_address" "$chain"
}

# Function to show usage
show_usage() {
    echo -e "\n${YELLOW}Usage:${NC}"
    echo "  $0 <token_address> <chain>"
    echo -e "\n${YELLOW}Supported chains:${NC} solana, ethereum, base, bnb, shibarium"
    echo -e "\n${YELLOW}Examples:${NC}"
    echo "  $0 EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v solana  # USDC on Solana"
    echo "  $0 0xA0b86a33E6417aB7f2a51833fBc13D3Be03D8Da0 ethereum  # USDC on Ethereum"
    echo "  $0 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 base     # USDC on Base"
    echo -e "\n${YELLOW}Quick test with known tokens:${NC}"
    echo "  $0 quick-solana    # Test with USDC on Solana"
    echo "  $0 quick-ethereum  # Test with USDC on Ethereum"
    echo "  $0 quick-base      # Test with USDC on Base"
}

# Parse arguments
if [[ $# -eq 0 ]]; then
    show_usage
    exit 1
elif [[ $# -eq 1 ]]; then
    case "$1" in
        "quick-solana")
            run_test "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v" "solana"
            ;;
        "quick-ethereum")
            run_test "0xA0b86a33E6417aB7f2a51833fBc13D3Be03D8Da0" "ethereum"
            ;;
        "quick-base")
            run_test "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913" "base"
            ;;
        *)
            echo -e "${RED}❌ Unknown quick test: $1${NC}"
            show_usage
            exit 1
            ;;
    esac
elif [[ $# -eq 2 ]]; then
    run_test "$1" "$2"
else
    echo -e "${RED}❌ Too many arguments${NC}"
    show_usage
    exit 1
fi

echo -e "\n${GREEN}🎉 Test completed!${NC}"