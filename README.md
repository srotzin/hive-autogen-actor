# hive-autogen-actor

![version](https://img.shields.io/badge/version-0.1.0-C08D23?labelColor=1a1a1a)
![python](https://img.shields.io/badge/python-3.10%2B-C08D23?labelColor=1a1a1a)
![license](https://img.shields.io/badge/license-MIT-C08D23?labelColor=1a1a1a)

AutoGen `ConversableAgent` subclass with Hive payment hooks pre-wired. Every tool call registers against the [Hive](https://hivemorph.onrender.com) agentic-commerce stack. Drop `HiveActor` into any AutoGen multi-agent workflow; Hive settlement fires on every tool invocation.

**Step 6 of the Hive TEN_STEPS_AHEAD plan — Wave C.**

---

## Install

```bash
pip install hive-autogen-actor
```

Python 3.10+.

---

## One-liner

```python
from hive_autogen_actor import HiveActor

actor = HiveActor(
    name="hive_buyer",
    monroe_address="0x15184bf50b3d3f52b60434f8942b7d52f2eb436e",
)
```

---

## Full example — AutoGen multi-agent with Hive settlement on every tool call

```python
import os
from autogen import UserProxyAgent
from hive_autogen_actor import HiveActor

os.environ.setdefault("HIVE_AGENT_DID", "did:hive:autogen-buyer")

# 1. Create the Hive actor with an LLM backend
hive_actor = HiveActor(
    name="hive_buyer",
    monroe_address="0x15184bf50b3d3f52b60434f8942b7d52f2eb436e",
    agent_did="did:hive:autogen-buyer",
    llm_config={
        "config_list": [
            {"model": "gpt-4o-mini", "api_key": os.environ["OPENAI_API_KEY"]}
        ],
        "temperature": 0,
    },
    system_message=(
        "You are a Hive purchasing agent. You use your Hive functions to "
        "browse the marketplace and build checkout carts. You always call "
        "hive_marketplace_list first, then hive_checkout_build to initiate payment."
    ),
)

# 2. User proxy drives the conversation
user_proxy = UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    max_consecutive_auto_reply=5,
    code_execution_config=False,
    is_termination_msg=lambda x: "TERMINATE" in x.get("content", ""),
)

# 3. Run a multi-turn conversation — every tool call is Hive-attributed
user_proxy.initiate_chat(
    hive_actor,
    message=(
        "Search the Hive marketplace for available tools, then build a "
        "checkout cart for the first result at 1000 atomic USDC. "
        "Return the checkout_id and x402 payment challenge. TERMINATE when done."
    ),
)

# 4. Direct API call (no conversation required)
cart = hive_actor.checkout_build(
    items=[{
        "tool_url": "https://hivemorph.onrender.com/v1/storefront/search",
        "est_amount_atomic": 1000,
    }],
    buyer_did="did:hive:autogen-buyer",
)
print("Checkout cart:", cart)
# → {"status_code": 200, "body": {"checkout_id": "...", "x402_challenge": {...}}}
```

---

## Pre-registered Hive functions

These AutoGen function specs are injected into `llm_config["functions"]` automatically:

| Function | Description | Payment required |
|---|---|---|
| `hive_marketplace_list` | List Hive marketplace listings | No |
| `hive_storefront_search` | Full-text search over Hive shapes | No |
| `hive_checkout_build` | Build x402 cart, get payment challenge | No |
| `hive_checkout_status` | Poll settlement status | No |
| `hive_receipt_verify` | Verify a Spectral-signed receipt | No |
| `hive_ad_decide` | Render winning IntraAgent ad for a tag | No |

---

## Direct API methods

`HiveActor` exposes the same functions as direct Python methods (no AutoGen conversation required):

```python
actor = HiveActor(name="x")
listings = actor.marketplace_list()
cart     = actor.checkout_build(items=[...])
ad       = actor.ad_decide(tag="data-tools")
```

---

## Live endpoints

| Surface | URL |
|---|---|
| Hive Marketplace | `https://hivemorph.onrender.com/v1/marketplace/list` |
| Hive Checkout build | `https://hive-checkout.onrender.com/v1/checkout/build` |
| Hive Checkout execute | `https://hive-checkout.onrender.com/v1/checkout/execute` |
| Hive Receipt sign | `https://hive-receipt.onrender.com/v1/receipt/sign` |
| Hive Ad decide | `https://hive-ad-bid.onrender.com/v1/ad/decide` |

---

## Request signing

Set `HIVE_AGENT_PRIVATE_KEY` (base64-encoded 32-byte ed25519 seed) for signed requests.

```bash
export HIVE_AGENT_PRIVATE_KEY="$(python3 -c 'import os,base64; print(base64.b64encode(os.urandom(32)).decode())')"
```

---

## Attribution

Every request carries `hive-referral: hive-autogen-actor/0.1.0`.

---

## Settlement

Base (chain ID 8453), USDC `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`. Monroe: `0x15184bf50b3d3f52b60434f8942b7d52f2eb436e`.

Council provenance: Wave C Step 6 — NEED + YIELD + CLEAN-MONEY passed.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Brand gold: #C08D23 (Pantone 1245 C). Settlement: Base USDC. Real rails only.*

Sources:
- Hive Checkout: https://hive-checkout.onrender.com/health
- Hive Receipt: https://hive-receipt.onrender.com/health
- Hive Ad Bid: https://hive-ad-bid.onrender.com/health
- x402 protocol: https://github.com/coinbase/x402
