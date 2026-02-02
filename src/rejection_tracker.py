"""
Token Rejection Tracker
Tracks tokens that have been analyzed and rejected to avoid re-analysis
Uses PostgreSQL storage
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from db import get_db_cursor, init_rejected_tokens_table


class RejectionTracker:
    """
    Tracks rejected tokens with reasons and timestamps
    Prevents re-analysis of recently rejected tokens
    """

    def __init__(self, ttl_days: int = 7):
        """
        Initialize rejection tracker

        Args:
            ttl_days: Days to keep rejections before expiring
        """
        self.ttl_days = ttl_days
        self._ensure_table_exists()
        self._clean_expired()

    def _ensure_table_exists(self):
        """Ensure the rejected_tokens table exists"""
        init_rejected_tokens_table()

    def _clean_expired(self):
        """Remove expired rejections based on TTL"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.ttl_days)

        with get_db_cursor() as cursor:
            cursor.execute(
                "DELETE FROM rejected_tokens WHERE timestamp < %s RETURNING token_key",
                (cutoff,)
            )
            deleted = cursor.fetchall()

        if deleted:
            print(f"🗑️ Cleaned {len(deleted)} expired token rejections")

    def add_rejection(
        self,
        token_address: str,
        chain: str,
        reason: str,
        symbol: Optional[str] = None,
        metadata: Optional[Dict] = None
    ):
        """
        Add a token rejection

        Args:
            token_address: Token contract address
            chain: Blockchain name
            reason: Rejection reason
            symbol: Token symbol
            metadata: Additional metadata
        """
        key = f"{chain}:{token_address.lower()}"
        now = datetime.now(timezone.utc)
        meta_json = json.dumps(metadata or {})

        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO rejected_tokens
                    (token_key, address, chain, reason, timestamp, metadata, symbol)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (token_key) DO UPDATE SET
                    reason = EXCLUDED.reason,
                    timestamp = EXCLUDED.timestamp,
                    metadata = EXCLUDED.metadata,
                    symbol = EXCLUDED.symbol
            """, (key, token_address, chain, reason, now, meta_json, symbol))

        symbol_str = f" ({symbol})" if symbol else ""
        print(f"❌ Rejected token {token_address[:8]}...{symbol_str} on {chain}: {reason}")

    def is_rejected(self, token_address: str, chain: str) -> bool:
        """
        Check if a token has been rejected

        Args:
            token_address: Token contract address
            chain: Blockchain name

        Returns:
            True if token was rejected within TTL period
        """
        key = f"{chain}:{token_address.lower()}"
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.ttl_days)

        with get_db_cursor(commit=False) as cursor:
            cursor.execute("""
                SELECT 1 FROM rejected_tokens
                WHERE token_key = %s AND timestamp > %s
            """, (key, cutoff))
            result = cursor.fetchone()

        return result is not None

    def get_rejection_reason(self, token_address: str, chain: str) -> Optional[str]:
        """
        Get rejection reason for a token

        Args:
            token_address: Token contract address
            chain: Blockchain name

        Returns:
            Rejection reason or None if not rejected
        """
        key = f"{chain}:{token_address.lower()}"

        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                "SELECT reason FROM rejected_tokens WHERE token_key = %s",
                (key,)
            )
            result = cursor.fetchone()

        return result["reason"] if result else None

    def get_rejected_tokens(self, chain: Optional[str] = None) -> List[Dict]:
        """
        Get list of all rejected tokens

        Args:
            chain: Optional chain filter

        Returns:
            List of rejection records
        """
        with get_db_cursor(commit=False) as cursor:
            if chain:
                cursor.execute("""
                    SELECT address, chain, reason, timestamp, metadata, symbol
                    FROM rejected_tokens WHERE chain = %s
                """, (chain,))
            else:
                cursor.execute("""
                    SELECT address, chain, reason, timestamp, metadata, symbol
                    FROM rejected_tokens
                """)
            rows = cursor.fetchall()

        return [
            {
                "address": row["address"],
                "chain": row["chain"],
                "reason": row["reason"],
                "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
                "metadata": row["metadata"] or {},
                "symbol": row["symbol"]
            }
            for row in rows
        ]

    def remove_rejection(self, token_address: str, chain: str):
        """
        Remove a token from rejection list

        Args:
            token_address: Token contract address
            chain: Blockchain name
        """
        key = f"{chain}:{token_address.lower()}"

        with get_db_cursor() as cursor:
            cursor.execute(
                "DELETE FROM rejected_tokens WHERE token_key = %s RETURNING token_key",
                (key,)
            )
            deleted = cursor.fetchone()

        if deleted:
            print(f"✅ Removed rejection for {token_address[:8]}... on {chain}")

    def clear_all(self):
        """Clear all rejections"""
        with get_db_cursor() as cursor:
            cursor.execute("DELETE FROM rejected_tokens")
        print("🗑️ Cleared all token rejections")

    def get_stats(self) -> Dict:
        """Get rejection statistics"""
        with get_db_cursor(commit=False) as cursor:
            # Total count
            cursor.execute("SELECT COUNT(*) as total FROM rejected_tokens")
            total = cursor.fetchone()["total"]

            # By chain
            cursor.execute("""
                SELECT chain, COUNT(*) as count
                FROM rejected_tokens GROUP BY chain
            """)
            by_chain = {row["chain"]: row["count"] for row in cursor.fetchall()}

            cursor.execute("""
                SELECT
                    SPLIT_PART(reason, ':', 1) as reason_key,
                    COUNT(*) as count
                FROM rejected_tokens GROUP BY reason_key
            """)
            by_reason = {row["reason_key"]: row["count"] for row in cursor.fetchall()}

        return {
            "total_rejected": total,
            "by_chain": by_chain,
            "by_reason": by_reason,
            "ttl_days": self.ttl_days
        }


# Singleton instance
_tracker_instance = None


def get_rejection_tracker(ttl_days: int = 7) -> RejectionTracker:
    """
    Get singleton rejection tracker instance

    Args:
        ttl_days: TTL for rejections

    Returns:
        RejectionTracker instance
    """
    global _tracker_instance

    if _tracker_instance is None:
        _tracker_instance = RejectionTracker(ttl_days)

    return _tracker_instance


# Standard rejection reasons
class RejectionReason:
    """Standard rejection reasons"""
    LOW_LIQUIDITY = "low_liquidity"
    HIGH_CONCENTRATION = "high_concentration"
    SUSPICIOUS_ACTIVITY = "suspicious_activity"
    FAILED_ANALYSIS = "failed_analysis"
    RUG_RISK = "rug_risk"
    LOW_HOLDER_COUNT = "low_holder_count"
    ABNORMAL_VOLUME = "abnormal_volume"
    CONTRACT_ISSUES = "contract_issues"
    BLACKLISTED = "blacklisted"
    BELOW_CRITERIA = "below_criteria"


if __name__ == "__main__":
    # Test the rejection tracker
    tracker = get_rejection_tracker()

    # Add some test rejections
    tracker.add_rejection(
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "solana",
        RejectionReason.LOW_LIQUIDITY,
        symbol="USDC",
        metadata={"liquidity": 10000}
    )

    tracker.add_rejection(
        "So11111111111111111111111111111111111111112",
        "solana",
        RejectionReason.HIGH_CONCENTRATION,
        symbol="SOL",
        metadata={"top_holder_percent": 85}
    )

    # Check if rejected
    print("\n📊 Rejection Stats:")
    print(json.dumps(tracker.get_stats(), indent=2))

    # Test lookup
    is_rejected = tracker.is_rejected(
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "solana"
    )
    print(f"\n✅ Token rejected: {is_rejected}")

    reason = tracker.get_rejection_reason(
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "solana"
    )
    print(f"📝 Reason: {reason}")
