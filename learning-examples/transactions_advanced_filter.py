import asyncio
import os
import sys
import grpc
import base58

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
    Main function that connects to Geyser and monitors all successful, non-vote transactions.
    """
    async with grpc.aio.secure_channel(
        GEYSER_ENDPOINT,
        grpc.composite_channel_credentials(
            grpc.ssl_channel_credentials(),
            grpc.metadata_call_credentials(
                lambda context, callback: callback((('x-token', GEYSER_API_TOKEN),), None)
            )
        )
    ) as channel:
        stub = geyser_pb2_grpc.GeyserStub(channel)

        # Basic transaction subscription for all successful, non-vote transactions
        request = geyser_pb2.SubscribeRequest(
            transactions={
                "transactions_filter": geyser_pb2.SubscribeRequestFilterTransactions(
                    # If all fields are empty then all transactions are broadcasted.
                    # Otherwise fields works as logical AND and values in arrays as logical OR.
                    vote=False,  # Exclude vote transactions
                    failed=False,  # Exclude failed transactions
                    account_include=[RAYDIUM_MARKET_ADDRESS], # Use this to ensure that ANY account is included
                    account_exclude=[], # Use this to exclude specific accounts
                    account_required=[] # Use this to ensure ALL accounts are included
                )
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )

        print("🚀 Starting transaction monitor for all transactions...")
        print("📡 Listening for transactions...")
        print("---")

        update_count = 0
        async for response in stub.Subscribe(iter([request])):
            update_count += 1
            
            if response.transaction:
                tx_info = response.transaction
                
                print(f"💸 Transaction Update #{update_count}")
                print(f"   Signature: {base58.b58encode(tx_info.transaction.signature).decode('utf-8')}")
                print(f"   Slot: {tx_info.slot}")
                print("---")
            else:
                print(f"⚠️  Received non-transaction update: {response}")
                print("---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
