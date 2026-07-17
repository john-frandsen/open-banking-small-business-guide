#!/usr/bin/env python3
"""Consolidate balances and transactions across multiple bank connections.

Demonstrates the PSD2 Account Information Service (AIS) aggregation pattern.
Requires: httpx (pip install httpx). Set env vars for each connection's API base + token.
"""
import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
try:
    import httpx
except ImportError:
    raise SystemExit("pip install httpx")


@dataclass
class BankConnection:
    name: str          # e.g. "Starling", "Revolut Business"
    api_base: str      # aggregator or direct bank API base URL
    access_token: str


def fetch_accounts(conn: BankConnection) -> list[dict]:
    """List accounts for a single connection."""
    r = httpx.get(
        f"{conn.api_base}/accounts",
        headers={"Authorization": f"Bearer {conn.access_token}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("accounts", [])


def fetch_balance(conn: BankConnection, account_id: str) -> dict:
    r = httpx.get(
        f"{conn.api_base}/accounts/{account_id}/balances",
        headers={"Authorization": f"Bearer {conn.access_token}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["balances"][0]


def fetch_transactions(conn: BankConnection, account_id: str) -> list[dict]:
    r = httpx.get(
        f"{conn.api_base}/accounts/{account_id}/transactions",
        headers={"Authorization": f"Bearer {conn.access_token}"},
        params={"limit": 100},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("transactions", [])


def consolidate(connections: list[BankConnection]) -> dict:
    """Pull every account across every bank into one view."""
    snapshot = {"fetched_at": datetime.now(timezone.utc).isoformat(), "accounts": []}
    total = 0.0

    for conn in connections:
        for acct in fetch_accounts(conn):
            acct_id = acct["id"]
            balance = fetch_balance(conn, acct_id)
            amount = float(balance["amount"])
            total += amount

            snapshot["accounts"].append({
                "bank": conn.name,
                "nickname": acct.get("nickname", acct_id),
                "iban": acct.get("iban"),
                "currency": balance["currency"],
                "balance": amount,
                "tx_count": len(fetch_transactions(conn, acct_id)),
            })

    snapshot["total_cash"] = round(total, 2)
    return snapshot


if __name__ == "__main__":
    connections = [
        BankConnection("Starling", os.environ["STARLING_API"], os.environ["STARLING_TOKEN"]),
        BankConnection("Revolut", os.environ["REVOLUT_API"], os.environ["REVOLUT_TOKEN"]),
    ]
    print(json.dumps(consolidate(connections), indent=2))
