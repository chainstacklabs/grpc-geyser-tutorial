import asyncio
import os
import sys
import grpc
import base58

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from generated import geyser_pb2, geyser_pb2_grpc

load_dotenv()


GEYSER_ENDPOINT = os.getenv("GEYSER_ENDPOINT")
GEYSER_API_TOKEN = os.getenv("GEYSER_API_TOKEN")

# This is the Raydium (WSOL-RAY) market address.
# We will subscribe to updates for this specific account.
RAYDIUM_MARKET_ADDRESS = "2AXXcN6oN9bBT5owwmTH53C7QHUXvhLeu718Kqt8rvY2"


async def main():
    """
    Main function that connects to Geyser and monitors a specific account.

    This will receive updates whenever the specified account's data changes.
    """
    async with grpc.aio.secure_channel(
        GEYSER_ENDPOINT,
        grpc.composite_channel_credentials(
            grpc.ssl_channel_credentials(),
            grpc.metadata_call_credentials(
                lambda context, callback: callback(
                    (("x-token", GEYSER_API_TOKEN),), None
                )
            ),
        ),
    ) as channel:
        stub = geyser_pb2_grpc.GeyserStub(channel)

        # Create subscription request to monitor a specific account
        request = geyser_pb2.SubscribeRequest(
            accounts={
                "accounts_filter": geyser_pb2.SubscribeRequestFilterAccounts(
                    # Provide the specific account public key to monitor
                    account=[RAYDIUM_MARKET_ADDRESS]
                )
            },
            # Use PROCESSED commitment for faster updates (vs CONFIRMED or FINALIZED)
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )

        print(f"🚀 Starting account monitor for: {RAYDIUM_MARKET_ADDRESS}")
        print("📡 Listening for updates...")
        print("---")

        update_count = 0
        async for response in stub.Subscribe(iter([request])):
            update_count += 1

            if response.account:
                account_info = response.account.account

                print(f"📊 Update #{update_count}")
                print(
                    f"   Account: {base58.b58encode(account_info.pubkey).decode('utf-8')}"
                )
                print(f"   Lamports: {account_info.lamports:,}")
                print(f"   Data Size: {len(account_info.data)} bytes")
                print(
                    f"   Owner: {base58.b58encode(account_info.owner).decode('utf-8')}"
                )
                print("---")
            else:
                print(f"⚠️  Received non-account update: {response}")
                print("---")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
