"""
hive-autogen-actor
==================
AutoGen ConversableAgent subclass with Hive payment hooks:
  - hive-marketplace  (capability discovery)
  - hive-checkout     (cart / bundle settlement via x402)
  - hive-receipt      (Spectral-signed receipts)
  - hive-ad-bid       (IntraAgent ad slot rendering)

One-liner::

    from hive_autogen_actor import HiveActor
    actor = HiveActor(
        name="hive_buyer",
        monroe_address="0x15184bf50b3d3f52b60434f8942b7d52f2eb436e",
    )

Brand gold: #C08D23 (Pantone 1245 C).  NEVER #f5c518.
"""

from hive_autogen_actor.actor import HiveActor
from hive_autogen_actor.client import HiveClient

__version__ = "0.1.0"
__all__ = ["HiveActor", "HiveClient"]
