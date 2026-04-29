"""
HiveClient — low-level httpx wrapper for all four Hive surfaces.
(AutoGen package edition — identical transport layer, different referral tag.)

All requests carry:
  - hive-referral: hive-autogen-actor/0.1.0
  - ed25519 request signature (X-Hive-Sig) if HIVE_AGENT_PRIVATE_KEY is set
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any

import httpx

MARKETPLACE_BASE = "https://hivemorph.onrender.com"
CHECKOUT_BASE    = "https://hive-checkout.onrender.com"
RECEIPT_BASE     = "https://hive-receipt.onrender.com"
AD_BID_BASE      = "https://hive-ad-bid.onrender.com"

REFERRAL_TAG     = "hive-autogen-actor/0.1.0"
BRAND_GOLD       = "#C08D23"  # Pantone 1245 C — never #f5c518


def _load_private_key():
    raw = os.environ.get("HIVE_AGENT_PRIVATE_KEY")
    if not raw:
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return Ed25519PrivateKey.from_private_bytes(base64.b64decode(raw))
    except Exception:
        return None


def _sign_request(body: bytes, private_key) -> str | None:
    if private_key is None:
        return None
    try:
        sig = private_key.sign(hashlib.sha256(body).digest())
        return base64.b64encode(sig).decode()
    except Exception:
        return None


class HiveClient:
    """Thin httpx client for Hive endpoints (AutoGen edition)."""

    MONROE_DEFAULT = "0x15184bf50b3d3f52b60434f8942b7d52f2eb436e"

    def __init__(
        self,
        monroe_address: str | None = None,
        agent_did: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self.monroe = monroe_address or self.MONROE_DEFAULT
        self.agent_did = agent_did or os.environ.get("HIVE_AGENT_DID", "did:hive:anonymous")
        self._private_key = _load_private_key()
        self._timeout = timeout
        self._http = httpx.Client(timeout=timeout)

    def _base_headers(self, body: bytes = b"") -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type":     "application/json",
            "hive-referral":    REFERRAL_TAG,
            "X-Hive-Agent-DID": self.agent_did,
            "X-Hive-Monroe":    self.monroe,
            "X-Hive-Ts":        str(int(time.time())),
        }
        sig = _sign_request(body, self._private_key)
        if sig:
            headers["X-Hive-Sig"] = sig
        return headers

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode()
        resp = self._http.post(url, content=body, headers=self._base_headers(body))
        return {"status_code": resp.status_code, "body": resp.json() if resp.content else {}}

    def _get(self, url: str, params: dict | None = None) -> dict[str, Any]:
        resp = self._http.get(url, params=params, headers=self._base_headers())
        return {"status_code": resp.status_code, "body": resp.json() if resp.content else {}}

    async def _apost(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload).encode()
        async with httpx.AsyncClient(timeout=self._timeout) as ac:
            resp = await ac.post(url, content=body, headers=self._base_headers(body))
        return {"status_code": resp.status_code, "body": resp.json() if resp.content else {}}

    async def _aget(self, url: str, params: dict | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as ac:
            resp = await ac.get(url, params=params, headers=self._base_headers())
        return {"status_code": resp.status_code, "body": resp.json() if resp.content else {}}

    def marketplace_list(self) -> dict[str, Any]:
        return self._get(f"{MARKETPLACE_BASE}/v1/marketplace/list")

    async def marketplace_list_async(self) -> dict[str, Any]:
        return await self._aget(f"{MARKETPLACE_BASE}/v1/marketplace/list")

    def storefront_search(self, query: str = "") -> dict[str, Any]:
        return self._get(f"{MARKETPLACE_BASE}/v1/storefront/search", params={"q": query} if query else None)

    def checkout_build(self, items: list[dict], buyer_did: str | None = None) -> dict[str, Any]:
        return self._post(f"{CHECKOUT_BASE}/v1/checkout/build", {
            "items": items, "buyer_did": buyer_did or self.agent_did,
        })

    async def checkout_build_async(self, items: list[dict], buyer_did: str | None = None) -> dict[str, Any]:
        return await self._apost(f"{CHECKOUT_BASE}/v1/checkout/build", {
            "items": items, "buyer_did": buyer_did or self.agent_did,
        })

    def checkout_execute(self, checkout_id: str, payment_proof: dict) -> dict[str, Any]:
        return self._post(f"{CHECKOUT_BASE}/v1/checkout/execute", {
            "checkout_id": checkout_id, "payment": payment_proof,
        })

    def checkout_status(self, checkout_id: str) -> dict[str, Any]:
        return self._get(f"{CHECKOUT_BASE}/v1/checkout/{checkout_id}/status")

    def receipt_sign(self, tx_hash: str, payer_did: str, payee_did: str,
                     amount_usdc: str, tool_id: str,
                     payment_proof: dict | None = None) -> dict[str, Any]:
        payload = {
            "tx_hash": tx_hash, "payer_did": payer_did,
            "payee_did": payee_did, "amount_usdc": amount_usdc,
            "tool_id": tool_id,
        }
        body = json.dumps(payload).encode()
        headers = self._base_headers(body)
        if payment_proof:
            headers["X-Payment"] = base64.b64encode(
                json.dumps(payment_proof).encode()
            ).decode()
        resp = self._http.post(f"{RECEIPT_BASE}/v1/receipt/sign", content=body, headers=headers)
        return {"status_code": resp.status_code, "body": resp.json() if resp.content else {}}

    def receipt_verify(self, receipt_id: str) -> dict[str, Any]:
        return self._get(f"{RECEIPT_BASE}/v1/receipt/verify/{receipt_id}")

    def ad_bid(self, advertiser_did: str, tag: str, headline: str,
               link: str, max_cpm_atomic: int, expires_at: str) -> dict[str, Any]:
        return self._post(f"{AD_BID_BASE}/v1/ad/bid", {
            "advertiser_did": advertiser_did, "tag": tag,
            "headline": headline, "link": link,
            "max_cpm_atomic": max_cpm_atomic, "expires_at": expires_at,
        })

    def ad_decide(self, publisher_did: str, tag: str, context: str = "") -> dict[str, Any]:
        return self._post(f"{AD_BID_BASE}/v1/ad/decide", {
            "publisher_did": publisher_did, "tag": tag, "context": context,
        })

    async def ad_decide_async(self, publisher_did: str, tag: str, context: str = "") -> dict[str, Any]:
        return await self._apost(f"{AD_BID_BASE}/v1/ad/decide", {
            "publisher_did": publisher_did, "tag": tag, "context": context,
        })

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "HiveClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
