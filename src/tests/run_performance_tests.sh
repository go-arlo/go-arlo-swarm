#!/bin/bash

# Performance test runner script
# Quick and easy way to run performance tests

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 GoArlo API Performance Test Runner${NC}"
echo -e "${BLUE}======================================${NC}\n"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")"

# Check for Python
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}❌ No Python found${NC}"
    exit 1
fi

# Check if server is running
check_server() {
    local url="${1:-http://localhost:8000}"
    echo -e "${YELLOW}Checking if server is running at $url...${NC}"
    
    if curl -s "$url/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Server is running${NC}\n"
        return 0
    else
        echo -e "${RED}❌ Server is not running${NC}"
        echo -e "${YELLOW}Please start the server first:${NC}"
        echo -e "  cd $SRC_DIR"
        echo -e "  python main.py\n"
        return 1
    fi
}

# Function to run test
run_test() {
    local test_name="$1"
    shift
    
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${CYAN}📊 Running: $test_name${NC}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
    
    cd "$SCRIPT_DIR"
    $PYTHON_CMD test_performance.py "$@"
    
    echo -e "\n${GREEN}✅ $test_name completed${NC}\n"
}

# Show menu
show_menu() {
    echo -e "${YELLOW}Select a test to run:${NC}\n"
    echo "  1) Quick Test (30 requests over 60s)"
    echo "  2) Concurrent Requests (20 simultaneous)"
    echo "  3) Cache Effectiveness"
    echo "  4) Stress Test (Multi-channel simulation)"
    echo "  5) Custom Load Test"
    echo "  6) All Tests"
    echo "  7) Exit"
    echo ""
}

# Interactive mode
interactive_mode() {
    local base_url="${1:-http://localhost:8000}"
    
    if ! check_server "$base_url"; then
        exit 1
    fi
    
    while true; do
        show_menu
        read -p "Enter your choice (1-7): " choice
        echo ""
        
        case $choice in
            1)
                run_test "Quick Test" --base-url "$base_url"
                ;;
            2)
                run_test "Concurrent Requests Test" --base-url "$base_url" --concurrent 20
                ;;
            3)
                run_test "Cache Effectiveness Test" --base-url "$base_url" --test-cache
                ;;
            4)
                run_test "Stress Test" --base-url "$base_url" --stress-test
                ;;
            5)
                read -p "Enter number of requests: " requests
                read -p "Enter duration in seconds: " duration
                run_test "Custom Load Test" --base-url "$base_url" --requests "$requests" --duration "$duration"
                ;;
            6)
                run_test "All Tests" --base-url "$base_url" --all
                ;;
            7)
                echo -e "${GREEN}👋 Goodbye!${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}❌ Invalid choice. Please try again.${NC}\n"
                ;;
        esac
        
        echo -e "\n${YELLOW}Press Enter to continue...${NC}"
        read
        echo ""
    done
}

# Parse command line arguments
if [[ $# -eq 0 ]]; then
    # No arguments - run interactive mode
    interactive_mode
else
    case "$1" in
        --help|-h)
            echo -e "${YELLOW}Usage:${NC}"
            echo "  $0                           # Interactive mode"
            echo "  $0 quick                     # Quick test (30 requests over 60s)"
            echo "  $0 concurrent [N]            # Test N concurrent requests (default: 20)"
            echo "  $0 cache                     # Test cache effectiveness"
            echo "  $0 stress                    # Run stress test"
            echo "  $0 custom N SECONDS          # Custom load test"
            echo "  $0 all                       # Run all tests"
            echo "  $0 production                # Test against production (uses PUBLIC_URL env)"
            echo ""
            echo -e "${YELLOW}Examples:${NC}"
            echo "  $0 quick"
            echo "  $0 concurrent 30"
            echo "  $0 custom 50 60"
            echo "  $0 production"
            exit 0
            ;;
        quick)
            check_server && run_test "Quick Test"
            ;;
        concurrent)
            N="${2:-20}"
            check_server && run_test "Concurrent Requests Test" --concurrent "$N"
            ;;
        cache)
            check_server && run_test "Cache Test" --test-cache
            ;;
        stress)
            check_server && run_test "Stress Test" --stress-test
            ;;
        custom)
            if [[ $# -lt 3 ]]; then
                echo -e "${RED}❌ Usage: $0 custom REQUESTS DURATION${NC}"
                exit 1
            fi
            check_server && run_test "Custom Load Test" --requests "$2" --duration "$3"
            ;;
        all)
            check_server && run_test "All Tests" --all
            ;;
        production|prod)
            # Use PUBLIC_URL environment variable or prompt user
            if [[ -n "$PUBLIC_URL" ]]; then
                production_url="$PUBLIC_URL"
                echo -e "${GREEN}✅ Using PUBLIC_URL: $production_url${NC}"
            else
                read -p "Enter production deployment URL: " production_url
                if [[ -z "$production_url" ]]; then
                    echo -e "${RED}❌ No URL provided. Set PUBLIC_URL env var or enter URL.${NC}"
                    exit 1
                fi
            fi
            
            read -p "Enter API key (or press Enter to skip): " api_key
            
            if ! check_server "$production_url"; then
                exit 1
            fi
            
            if [[ -n "$api_key" ]]; then
                run_test "Production Test" --base-url "$production_url" --api-key "$api_key"
            else
                run_test "Production Test" --base-url "$production_url"
            fi
            ;;
        *)
            echo -e "${RED}❌ Unknown command: $1${NC}"
            echo "Run with --help for usage information"
            exit 1
            ;;
    esac
fi

echo -e "${GREEN}🎉 All tests completed!${NC}"

