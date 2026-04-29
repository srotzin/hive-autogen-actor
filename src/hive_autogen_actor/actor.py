"""
HiveActor — AutoGen ConversableAgent subclass with Hive payment hooks.

Usage::

    from autogen import AssistantAgent, UserProxyAgent
    from hive_autogen_actor import HiveActor

    hive_actor = HiveActor(
        name="hive_buyer",
        monroe_address="0x15184bf50b3d3f52b60434f8942b7d52f2eb436e",
        llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": "..."}]},
    )

    # In a multi-agent conversation, hive_actor can pay for every tool call
    # automatically via the Hive x402 checkout flow.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

try:
    from autogen import ConversableAgent
    _AUTOGEN_AVAILABLE = True
except ImportError:
    # Provide a minimal fallback so the package can be imported without autogen
    # installed (e.g. in a LangChain-only environment).
    _AUTOGEN_AVAILABLE = False

    class ConversableAgent:  # type: ignore[no-redef]
        """Stub for environments without autogen installed."""
        def __init__(self, name: str, **kwargs: Any) -> None:
            self.name = name


from hive_autogen_actor.client import HiveClient

# ── Hive function specs (registered as AutoGen tools) ─────────────────────────

HIVE_FUNCTION_MAP: dict[str, dict] = {
    "hive_marketplace_list": {
        "name": "hive_marketplace_list",
        "description": "List available tools and services in the Hive marketplace. No payment required.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "hive_storefront_search": {
        "name": "hive_storefront_search",
        "description": "Full-text search over Hive shapes / services. Returns matching services.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string, e.g. 'yield optimization' or 'settlement'.",
                },
            },
            "required": ["query"],
        },
    },
    "hive_checkout_build": {
        "name": "hive_checkout_build",
        "description": (
            "Build an x402 payment cart for one or more Hive tool calls. "
            "Returns a checkout_id and an x402 payment challenge. "
            "Call this before executing a paid Hive tool."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "description": (
                        "List of items to purchase. Each item must have "
                        "'tool_url' (string) and 'est_amount_atomic' (integer, USDC atomic units)."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_url": {"type": "string"},
                            "est_amount_atomic": {"type": "integer"},
                        },
                        "required": ["tool_url", "est_amount_atomic"],
                    },
                },
                "buyer_did": {
                    "type": "string",
                    "description": "DID of the purchasing agent. Optional.",
                },
            },
            "required": ["items"],
        },
    },
    "hive_checkout_status": {
        "name": "hive_checkout_status",
        "description": "Poll the settlement status of a Hive checkout cart by its checkout_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "checkout_id": {
                    "type": "string",
                    "description": "The checkout_id returned by hive_checkout_build.",
                },
            },
            "required": ["checkout_id"],
        },
    },
    "hive_receipt_verify": {
        "name": "hive_receipt_verify",
        "description": "Verify a Spectral-signed Hive receipt by its receipt_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "receipt_id": {
                    "type": "string",
                    "description": "The receipt ID to verify.",
                },
            },
            "required": ["receipt_id"],
        },
    },
    "hive_ad_decide": {
        "name": "hive_ad_decide",
        "description": "Render the winning IntraAgent ad slot for a given tag. Returns headline, link, and impression receipt.",
        "parameters": {
            "type": "object",
            "properties": {
                "tag": {
                    "type": "string",
                    "description": "Ad tag / category, e.g. 'data-tools', 'settlement', 'general'.",
                },
                "context": {
                    "type": "string",
                    "description": "Optional free-text context describing what the agent is doing.",
                },
            },
            "required": ["tag"],
        },
    },
}


# ── HiveActor ────────────────────────────────────────────────────────────────

class HiveActor(ConversableAgent):
    """
    AutoGen ConversableAgent subclass with Hive payment hooks.

    Every tool call function registered on this agent automatically carries
    the ``hive-referral`` header. When ``HIVE_AGENT_PRIVATE_KEY`` is set,
    requests are signed with ed25519.

    Six Hive functions are pre-registered:
      - ``hive_marketplace_list``   — browse the marketplace
      - ``hive_storefront_search``  — search Hive services
      - ``hive_checkout_build``     — open an x402 cart (returns payment challenge)
      - ``hive_checkout_status``    — poll cart settlement
      - ``hive_receipt_verify``     — verify a Spectral receipt
      - ``hive_ad_decide``          — render an IntraAgent ad slot

    Args:
        name: Agent name (passed to AutoGen).
        monroe_address: Hive Monroe settlement address.
        agent_did: DID of this actor.
        llm_config: AutoGen LLM config dict (optional).
        **kwargs: Forwarded to ``ConversableAgent.__init__``.

    Example::

        from autogen import UserProxyAgent
        from hive_autogen_actor import HiveActor

        hive_actor = HiveActor(
            name="hive_buyer",
            monroe_address="0x15184bf50b3d3f52b60434f8942b7d52f2eb436e",
            llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": "..."}]},
        )
        user_proxy = UserProxyAgent(
            name="user",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=3,
            code_execution_config=False,
        )
        user_proxy.initiate_chat(
            hive_actor,
            message="Search the Hive marketplace and tell me what tools are available.",
        )
    """

    MONROE_DEFAULT = "0x15184bf50b3d3f52b60434f8942b7d52f2eb436e"

    def __init__(
        self,
        name: str = "hive_actor",
        monroe_address: str | None = None,
        agent_did: str | None = None,
        llm_config: dict[str, Any] | bool | None = False,
        **kwargs: Any,
    ) -> None:
        self.monroe_address = monroe_address or self.MONROE_DEFAULT
        self.agent_did = agent_did or os.environ.get("HIVE_AGENT_DID", f"did:hive:{name}")
        self._hive_client = HiveClient(
            monroe_address=self.monroe_address,
            agent_did=self.agent_did,
        )

        # Build the function map for AutoGen
        function_map = self._build_function_map()

        # Build llm_config with function definitions if provided
        if llm_config and isinstance(llm_config, dict):
            existing_functions = llm_config.get("functions", [])
            llm_config = {
                **llm_config,
                "functions": existing_functions + list(HIVE_FUNCTION_MAP.values()),
            }

        if _AUTOGEN_AVAILABLE:
            super().__init__(
                name=name,
                llm_config=llm_config,
                function_map=function_map,
                **kwargs,
            )
        else:
            self.name = name

    def _build_function_map(self) -> dict[str, Callable]:
        """Return a dict mapping function names to callables for AutoGen."""
        client = self._hive_client

        def hive_marketplace_list() -> str:
            result = client.marketplace_list()
            return json.dumps(result, indent=2)

        def hive_storefront_search(query: str) -> str:
            result = client.storefront_search(query=query)
            return json.dumps(result, indent=2)

        def hive_checkout_build(items: list[dict], buyer_did: str | None = None) -> str:
            result = client.checkout_build(items=items, buyer_did=buyer_did)
            return json.dumps(result, indent=2)

        def hive_checkout_status(checkout_id: str) -> str:
            result = client.checkout_status(checkout_id=checkout_id)
            return json.dumps(result, indent=2)

        def hive_receipt_verify(receipt_id: str) -> str:
            result = client.receipt_verify(receipt_id=receipt_id)
            return json.dumps(result, indent=2)

        def hive_ad_decide(tag: str, context: str = "") -> str:
            result = client.ad_decide(
                publisher_did=self.agent_did,
                tag=tag,
                context=context,
            )
            return json.dumps(result, indent=2)

        return {
            "hive_marketplace_list":   hive_marketplace_list,
            "hive_storefront_search":  hive_storefront_search,
            "hive_checkout_build":     hive_checkout_build,
            "hive_checkout_status":    hive_checkout_status,
            "hive_receipt_verify":     hive_receipt_verify,
            "hive_ad_decide":          hive_ad_decide,
        }

    # ── Direct call helpers (usable without AutoGen) ─────────────────────────

    def marketplace_list(self) -> dict[str, Any]:
        """Directly call hive marketplace list (no AutoGen conversation required)."""
        return self._hive_client.marketplace_list()

    def storefront_search(self, query: str) -> dict[str, Any]:
        return self._hive_client.storefront_search(query=query)

    def checkout_build(self, items: list[dict], buyer_did: str | None = None) -> dict[str, Any]:
        return self._hive_client.checkout_build(items=items, buyer_did=buyer_did)

    def checkout_status(self, checkout_id: str) -> dict[str, Any]:
        return self._hive_client.checkout_status(checkout_id=checkout_id)

    def receipt_verify(self, receipt_id: str) -> dict[str, Any]:
        return self._hive_client.receipt_verify(receipt_id=receipt_id)

    def ad_decide(self, tag: str, context: str = "") -> dict[str, Any]:
        return self._hive_client.ad_decide(
            publisher_did=self.agent_did, tag=tag, context=context,
        )
