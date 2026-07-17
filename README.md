# Open Banking for Small Business: Aggregating Bank Accounts in Python

*A developer-focused guide to pulling balances and transactions from multiple banks into a single consolidated view under PSD2.*

A typical small business doesn't bank in one place. The operating account sits with one bank, a savings or reserve account with another, a business credit card with a third, and maybe a multi-currency account with a fourth. At month end, someone — usually the founder or a part-time bookkeeper — logs into four separate portals, exports four CSVs, and stitches it all together in a spreadsheet just to answer one question: *how much cash do we actually have, and where is it?*

This is the exact problem Open Banking was designed to solve. In this article we'll build a small but real piece of that solution: a Python script that pulls balances and recent transactions from multiple banks into a single consolidated view. It's a developer-focused take on **open banking for small business** — less "what is it" and more "here's the code."

## The framework: PSD2 and Account Information Services

Under PSD2 (and the UK's Open Banking standard), regulated providers can offer **Account Information Services (AIS)** — read-only access to a customer's bank accounts, granted with the customer's explicit consent. The properties that matter for a small business:

- **Customer-initiated consent.** The business owner authorizes access through their bank's own login flow. You never see their password.
- **Read-only by default.** AIS grants are separate from payment initiation. You can see balances and transactions; you cannot move money.
- **Revocable and scoped.** Consent can be limited to specific accounts and a specific duration, and revoked at any time from the bank's app.

For a small business, a single authorized connection can replace four manual logins — and it's fully auditable, which an accountant will appreciate.

## How aggregation actually works

Whether you connect directly to a bank or through an aggregator (Plaid, TrueLayer, Tink, GoCardless/Nordigen), the flow is identical:

1. **Consent / authorisation.** The user is redirected to their bank, logs in, and approves the requested scopes (for example `accounts balances transactions`).
2. **Callback + token exchange.** The bank redirects back to your app with a code; you exchange it for an access token (and a refresh token).
3. **Fetch.** You call the bank's API with the token to list accounts, then fetch balances and transactions per account.
4. **Refresh.** Access tokens are short-lived (often 5–30 minutes in the EU). You use the refresh token (long-lived, around 90 days) to mint new access tokens on a schedule.

That fourth step is what turns a one-off export into a living dashboard.

## The code

Below is a minimal but realistic implementation. It assumes you've already completed the consent flow and hold an access token, but it shows the full pattern for pulling and consolidating data across multiple banks.

```python
import os
import json
from dataclasses import dataclass
from datetime import datetime, timezone
import httpx

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
```

Run it and you get a single JSON snapshot: every account, across every bank, plus a `total_cash` figure — the number the spreadsheet was trying to compute by hand.

A quick `curl` sanity check for a single account's balance:

```bash
curl -s -H "Authorization: Bearer $STARLING_TOKEN" \
  "$STARLING_API/accounts/abc-123/balances"
```

## Practical things that will bite you

A few realities that don't appear in the happy-path code:

- **EU direct connections need an eIDAS QTSP certificate** (often €1,000–3,000 per year). This is why most small teams route through an aggregator instead of connecting to each bank directly. The UK Open Banking directory is cheaper, but UK-only.
- **Consents expire.** EU long-lived consents are valid around 180 days and require re-authentication; some banks force 90-day strong-customer-authentication reconfirmation. Build a "reconnect" flow and notify the user before expiry, or your dashboard silently goes stale.
- **Rate limits and 429s.** Banks throttle aggressively. Add exponential backoff and cache balances for a few minutes rather than hitting the API on every page load.
- **Currency normalisation.** A multi-currency business needs FX conversion before summing `total_cash`. Don't sum mixed currencies naively.
- **Transaction idempotency.** When syncing into a database, key on the bank's `transaction_id`, not on date plus amount — duplicates and late-arriving corrections are common.

## Where to take it from here

The `consolidate()` function above is the seed of a real product. Schedule it daily with a cron job or Celery beat, store snapshots in Postgres, and you have a historical cash-flow chart. Add transaction categorization — a lightweight rules engine or a local model call — and you've got the backbone of a small-business finance tool.

The Open Banking rails are now mature enough that the hard part is no longer *getting the data*. It's productising it: the consent UX, the reconnection handling, and the currency and categorization edge cases are where the real work lives.

If you're building in this space, the fastest path is usually an aggregator for breadth (cover many banks on day one), combined with one or two direct connections for the banks that matter most to your customers — once the eIDAS cost is justified by volume. The result is exactly what small businesses have wanted for years: every account, in one place, without a single spreadsheet import.


---

## About

Written by **John Frandsen** — building [open-banking.io](https://open-banking.io), a certificate-free open banking API for SMBs and developers. This guide is vendor-neutral; the code works with any PSD2-compliant endpoint or aggregator.

## License

MIT — use it however you like.
