import asyncio
import os
import sys
import grpc
import base58
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from generated import geyser_pb2, geyser_pb2_grpc

load_dotenv()

GEYSER_ENDPOINT = os.getenv("GEYSER_ENDPOINT")
GEYSER_API_TOKEN = os.getenv("GEYSER_API_TOKEN")

# This is the Raydium (WSOL-RAY) market address.
RAYDIUM_MARKET_ADDRESS = "2AXXcN6oN9bBT5owwmTH53C7QHUXvhLeu718Kqt8rvY2"


def decode_transaction_error(error_bytes):
    """Decode transaction error bytes to human-readable format"""
    if not error_bytes:
        return None

    try:
        # Try to decode as JSON first (common format)
        error_str = error_bytes.decode("utf-8")
        try:
            error_json = json.loads(error_str)
            return error_json
        except json.JSONDecodeError:
            return error_str
    except UnicodeDecodeError:
        # If not UTF-8, return hex representation
        return f"Binary error: {error_bytes.hex()}"


async def main():
    """
    Main function that connects to Geyser and monitors the status of all transactions.
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

        # Transaction status subscription - INCLUDE both success and failures
        request = geyser_pb2.SubscribeRequest(
            transactions_status={
                "transactions_filter": geyser_pb2.SubscribeRequestFilterTransactions(
                    vote=False,  # Exclude vote transactions
                    # failed=True,  # Include failed transactions
                    account_include=[
                        RAYDIUM_MARKET_ADDRESS
                    ],  # Use this to ensure that ANY account is included
                    account_exclude=[],  # Use this to exclude specific accounts
                    account_required=[],  # Use this to ensure ALL accounts are included
                )
            },
            commitment=geyser_pb2.CommitmentLevel.CONFIRMED,
        )

        print("🚀 Starting transaction status monitor...")
        print("📡 Listening for transaction statuses...")
        print("---")

        update_count = 0
        async for response in stub.Subscribe(iter([request])):
            update_count += 1

            if response.HasField("transaction_status"):  # Better way to check
                tx_status_info = response.transaction_status

                # Check if transaction has error
                has_error = tx_status_info.HasField("err") and tx_status_info.err.err

                print(f"🚦 Transaction Status Update #{update_count}")
                print(
                    f"   Signature: {base58.b58encode(tx_status_info.signature).decode('utf-8')}"
                )
                print(f"   Slot: {tx_status_info.slot}")
                print(f"   Is Vote: {tx_status_info.is_vote}")
                print(f"   Index: {tx_status_info.index}")
                print(f"   Status: {'Failed' if has_error else 'Success'}")
                print("---")
            else:
                print(
                    f"⚠️  Received non-transaction_status update: {type(response).__name__}"
                )
                print("---")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
