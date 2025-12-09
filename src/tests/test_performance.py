#!/usr/bin/env python3
"""
Performance Testing Suite for GoArlo API

Tests the following performance improvements:
1. Concurrency limiting (10 concurrent analyses via semaphore)
2. Cache effectiveness (5 min TTL)
3. Request deduplication
4. Load handling under stress

Usage:
    # Basic performance test
    python test_performance.py
    
    # Custom load test - 50 requests in 1 minute
    python test_performance.py --requests 50 --duration 60
    
    # Test concurrent requests
    python test_performance.py --concurrent 20
    
    # Test cache effectiveness
    python test_performance.py --test-cache
    
    # Full stress test
    python test_performance.py --stress-test
"""

import asyncio
import aiohttp
import argparse
import time
import statistics
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PerformanceTestResults:
    """Track and display performance test results"""
    
    def __init__(self):
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.rate_limited_requests = 0
        self.cached_responses = 0
        self.response_times: List[float] = []
        self.errors: Dict[str, int] = defaultdict(int)
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
    def record_request(
        self,
        success: bool,
        response_time: float,
        status_code: int,
        error: Optional[str] = None,
        was_cached: bool = False
    ):
        """Record a single request result"""
        self.total_requests += 1
        self.response_times.append(response_time)
        
        if status_code == 429:
            self.rate_limited_requests += 1
        elif success:
            self.successful_requests += 1
            if was_cached:
                self.cached_responses += 1
        else:
            self.failed_requests += 1
            if error:
                self.errors[error] += 1
    
    def start(self):
        """Start timing"""
        self.start_time = time.time()
    
    def stop(self):
        """Stop timing"""
        self.end_time = time.time()
    
    def print_summary(self):
        """Print comprehensive test results"""
        duration = self.end_time - self.start_time if self.end_time and self.start_time else 0
        
        print("\n" + "=" * 70)
        print("📊 PERFORMANCE TEST RESULTS")
        print("=" * 70)
        
        print(f"\n⏱️  Test Duration: {duration:.2f} seconds")
        print(f"\n📈 Request Statistics:")
        print(f"   Total Requests:      {self.total_requests}")
        print(f"   ✅ Successful:       {self.successful_requests} ({self.success_rate:.1f}%)")
        print(f"   ❌ Failed:           {self.failed_requests} ({self.failure_rate:.1f}%)")
        print(f"   🚫 Rate Limited:     {self.rate_limited_requests} ({self.rate_limit_rate:.1f}%)")
        print(f"   💾 Cached:           {self.cached_responses} ({self.cache_hit_rate:.1f}%)")
        
        if self.response_times:
            print(f"\n⚡ Response Times:")
            print(f"   Average:   {statistics.mean(self.response_times):.3f}s")
            print(f"   Median:    {statistics.median(self.response_times):.3f}s")
            print(f"   Min:       {min(self.response_times):.3f}s")
            print(f"   Max:       {max(self.response_times):.3f}s")
            if len(self.response_times) > 1:
                print(f"   Std Dev:   {statistics.stdev(self.response_times):.3f}s")
        
        print(f"\n🚀 Throughput:")
        if duration > 0:
            print(f"   Requests/sec:  {self.total_requests / duration:.2f}")
            print(f"   Success/sec:   {self.successful_requests / duration:.2f}")
        
        if self.errors:
            print(f"\n❌ Errors by Type:")
            for error, count in sorted(self.errors.items(), key=lambda x: x[1], reverse=True):
                print(f"   {error}: {count}")
        
        print("\n" + "=" * 70)
    
    @property
    def success_rate(self) -> float:
        return (self.successful_requests / self.total_requests * 100) if self.total_requests > 0 else 0
    
    @property
    def failure_rate(self) -> float:
        return (self.failed_requests / self.total_requests * 100) if self.total_requests > 0 else 0
    
    @property
    def rate_limit_rate(self) -> float:
        return (self.rate_limited_requests / self.total_requests * 100) if self.total_requests > 0 else 0
    
    @property
    def cache_hit_rate(self) -> float:
        return (self.cached_responses / self.successful_requests * 100) if self.successful_requests > 0 else 0


class PerformanceTester:
    """Performance testing client for GoArlo API"""
    
    def __init__(self, base_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.base_url = base_url
        self.api_key = api_key
        self.results = PerformanceTestResults()
        
        # Test tokens for various scenarios
        self.test_tokens = {
            "solana": [
                {
                    "text": "<<<@GoArloApp EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v>>>",
                    "link": "https://twitter.com/test/status/-1234567890",
                    "name": "USDC (Solana)"
                },
                {
                    "text": "<<<@GoArloApp So11111111111111111111111111111111111111112>>>",
                    "link": "https://twitter.com/test/status/-1234567891",
                    "name": "Wrapped SOL"
                },
                {
                    "text": "<<<@GoArloApp Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB>>>",
                    "link": "https://twitter.com/test/status/-1234567894",
                    "name": "USDT (Solana)"
                }
            ],
            "ethereum": [
                {
                    "text": "<<<@GoArloApp 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2>>>",
                    "link": "https://twitter.com/test/status/-1234567892",
                    "name": "WETH"
                },
                {
                    "text": "<<<@GoArloApp 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48>>>",
                    "link": "https://twitter.com/test/status/-1234567895",
                    "name": "USDC (Ethereum)"
                }
            ],
            "base": [
                {
                    "text": "<<<@GoArloApp 0x4200000000000000000000000000000000000006>>>",
                    "link": "https://twitter.com/test/status/-1234567893",
                    "name": "WETH on Base"
                },
                {
                    "text": "<<<@GoArloApp 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913>>>",
                    "link": "https://twitter.com/test/status/-1234567896",
                    "name": "USDC on Base"
                }
            ]
        }
    
    async def make_request(
        self,
        session: aiohttp.ClientSession,
        text: str,
        link: str,
        name: str = "Unknown"
    ) -> Dict[str, Any]:
        """Make a single API request and record results"""
        start_time = time.time()
        
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        
        try:
            async with session.post(
                f"{self.base_url}/api/extract-token",
                json={"text": text, "link": link},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=120)  # 2 min timeout
            ) as response:
                response_time = time.time() - start_time
                
                try:
                    data = await response.json()
                except:
                    data = {}
                
                # Check if response was cached (fast response time < 2s typically means cache hit)
                was_cached = response_time < 2.0 and response.status == 200
                
                self.results.record_request(
                    success=response.status in [200, 201],
                    response_time=response_time,
                    status_code=response.status,
                    error=data.get('detail') if response.status >= 400 else None,
                    was_cached=was_cached
                )
                
                return {
                    "success": response.status in [200, 201],
                    "status": response.status,
                    "response_time": response_time,
                    "name": name,
                    "was_cached": was_cached
                }
        
        except asyncio.TimeoutError:
            response_time = time.time() - start_time
            self.results.record_request(
                success=False,
                response_time=response_time,
                status_code=0,
                error="Timeout"
            )
            return {
                "success": False,
                "status": 0,
                "response_time": response_time,
                "name": name,
                "error": "Timeout"
            }
        
        except Exception as e:
            response_time = time.time() - start_time
            self.results.record_request(
                success=False,
                response_time=response_time,
                status_code=0,
                error=str(e)
            )
            return {
                "success": False,
                "status": 0,
                "response_time": response_time,
                "name": name,
                "error": str(e)
            }
    
    async def test_concurrent_requests(self, num_requests: int = 20):
        """Test concurrent request handling"""
        print(f"\n🔥 Testing {num_requests} concurrent requests...")
        print(f"   Expected: Max 10 concurrent analyses (semaphore limit)")
        
        self.results = PerformanceTestResults()
        self.results.start()
        
        # Use same token to test deduplication
        test_data = self.test_tokens["solana"][0]
        
        async with aiohttp.ClientSession() as session:
            tasks = [
                self.make_request(session, test_data["text"], test_data["link"], f"Request {i+1}")
                for i in range(num_requests)
            ]
            
            results = await asyncio.gather(*tasks)
        
        self.results.stop()
        
        # Analyze concurrency behavior
        fast_responses = [r for r in results if r["response_time"] < 2.0]
        print(f"\n   Fast responses (<2s): {len(fast_responses)} (likely cached/deduplicated)")
        print(f"   Slow responses (>2s): {num_requests - len(fast_responses)} (actual analyses)")
        
        self.results.print_summary()
    
    
    async def test_cache_effectiveness(self):
        """Test cache effectiveness (5 min TTL)"""
        print(f"\n💾 Testing cache effectiveness...")
        print(f"   Expected: First request slow, subsequent fast (cached)")
        
        self.results = PerformanceTestResults()
        self.results.start()
        
        test_data = self.test_tokens["solana"][0]
        
        async with aiohttp.ClientSession() as session:
            # First request - should be slow (full analysis)
            print(f"\n   Request 1 (fresh): ", end="", flush=True)
            result1 = await self.make_request(session, test_data["text"], test_data["link"], "First")
            print(f"{result1['response_time']:.2f}s")
            
            # Wait a moment
            await asyncio.sleep(1)
            
            # Second request - should be fast (cached)
            print(f"   Request 2 (cached): ", end="", flush=True)
            result2 = await self.make_request(session, test_data["text"], test_data["link"], "Second")
            print(f"{result2['response_time']:.2f}s")
            
            # Third request - should still be fast (cached)
            print(f"   Request 3 (cached): ", end="", flush=True)
            result3 = await self.make_request(session, test_data["text"], test_data["link"], "Third")
            print(f"{result3['response_time']:.2f}s")
            
            speedup = result1['response_time'] / result2['response_time'] if result2['response_time'] > 0 else 0
            print(f"\n   ⚡ Cache speedup: {speedup:.1f}x faster")
        
        self.results.stop()
        self.results.print_summary()
    
    async def test_load_distribution(self, requests: int = 30, duration: int = 60):
        """Test load distributed over time"""
        print(f"\n📊 Testing {requests} requests over {duration} seconds...")
        print(f"   Rate: {requests / duration * 60:.1f} requests/minute")
        
        self.results = PerformanceTestResults()
        self.results.start()
        
        # Mix of tokens across chains
        all_tokens = []
        for chain_tokens in self.test_tokens.values():
            all_tokens.extend(chain_tokens)
        
        interval = duration / requests
        
        async with aiohttp.ClientSession() as session:
            for i in range(requests):
                token = all_tokens[i % len(all_tokens)]
                
                # Add timestamp for uniqueness
                unique_link = f"{token['link']}?t={int(time.time())}&n={i}"
                
                print(f"   Request {i+1}/{requests}... ", end="", flush=True)
                result = await self.make_request(
                    session,
                    token["text"],
                    unique_link,
                    f"Request {i+1}"
                )
                
                status_emoji = "✅" if result["success"] else "🚫" if result["status"] == 429 else "❌"
                print(f"{status_emoji} {result['response_time']:.2f}s")
                
                # Wait before next request
                if i < requests - 1:
                    await asyncio.sleep(interval)
        
        self.results.stop()
        self.results.print_summary()
    
    async def test_stress(self):
        """Full stress test - combines all scenarios"""
        print(f"\n💥 STRESS TEST - Simulating multiple Telegram channels")
        print(f"   Scenario: 5 channels, each sending 4 requests simultaneously")
        
        self.results = PerformanceTestResults()
        self.results.start()
        
        # Simulate 5 different channels
        channels = 5
        requests_per_channel = 4
        
        all_tokens = []
        for chain_tokens in self.test_tokens.values():
            all_tokens.extend(chain_tokens)
        
        async with aiohttp.ClientSession() as session:
            channel_tasks = []
            
            for channel_id in range(channels):
                # Each channel makes multiple requests
                channel_requests = []
                for req_id in range(requests_per_channel):
                    token = all_tokens[(channel_id * requests_per_channel + req_id) % len(all_tokens)]
                    unique_link = f"{token['link']}?ch={channel_id}&r={req_id}"
                    
                    channel_requests.append(
                        self.make_request(
                            session,
                            token["text"],
                            unique_link,
                            f"Channel{channel_id}-Req{req_id}"
                        )
                    )
                
                channel_tasks.extend(channel_requests)
            
            # Execute all requests concurrently
            results = await asyncio.gather(*channel_tasks)
        
        self.results.stop()
        
        print(f"\n   Total simultaneous requests: {channels * requests_per_channel}")
        print(f"   Concurrency limit: 10")
        print(f"   Expected: Requests queue and process smoothly")
        
        self.results.print_summary()


async def main():
    """Main test runner"""
    parser = argparse.ArgumentParser(
        description="Performance testing for GoArlo API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test concurrent requests
  python test_performance.py --concurrent 25
  
  # Test cache effectiveness
  python test_performance.py --test-cache
  
  # Custom load test
  python test_performance.py --requests 50 --duration 60
  
  # Full stress test
  python test_performance.py --stress-test
  
  # Run all tests
  python test_performance.py --all
        """
    )
    
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)"
    )
    parser.add_argument(
        "--api-key",
        help="API key for authentication (optional)"
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        metavar="N",
        help="Test N concurrent requests"
    )
    parser.add_argument(
        "--test-cache",
        action="store_true",
        help="Test cache effectiveness"
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=30,
        help="Number of requests for load test (default: 30)"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Duration in seconds for load test (default: 60)"
    )
    parser.add_argument(
        "--stress-test",
        action="store_true",
        help="Run full stress test (simulates multiple channels)"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all tests"
    )
    
    args = parser.parse_args()
    
    # Create tester
    tester = PerformanceTester(base_url=args.base_url, api_key=args.api_key)
    
    print("🚀 GoArlo API Performance Test Suite")
    print("=" * 70)
    print(f"Target: {args.base_url}")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Run selected tests
        if args.all or args.concurrent:
            await tester.test_concurrent_requests(args.concurrent or 20)
        
        if args.all or args.test_cache:
            await tester.test_cache_effectiveness()
        
        if args.all or (not args.concurrent and not args.test_cache and not args.stress_test):
            # Default: load distribution test
            await tester.test_load_distribution(args.requests, args.duration)
        
        if args.all or args.stress_test:
            await tester.test_stress()
        
        print("\n✅ All tests completed!")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

