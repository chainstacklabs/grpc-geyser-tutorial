import asyncio
import os
import sys
import grpc

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from dotenv import load_dotenv
from generated import geyser_pb2, geyser_pb2_grpc

load_dotenv()


GEYSER_ENDPOINT = os.getenv("GEYSER_ENDPOINT")
GEYSER_API_TOKEN = os.getenv("GEYSER_API_TOKEN")

async def main():
    """
    Main function that connects to Geyser and subscribes to ledger entries.
    
    This provides a low-level stream of ledger updates as they are processed by the validator.
    It is a high-throughput stream and does not offer filtering.
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

        # Entry subscription (no filtering available)
        request = geyser_pb2.SubscribeRequest(
            entry={
                "entry_filter": geyser_pb2.SubscribeRequestFilterEntry()
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )

        print("🚀 Starting entry subscription...")
        print("📡 Listening for ledger entries...")
        print("---")

        update_count = 0
        async for response in stub.Subscribe(iter([request])):
            update_count += 1
            
            if response.entry:
                entry_info = response.entry
                
                print(f"🎟️ Entry Update #{update_count}")
                print(f"   Slot: {entry_info.slot}")
                print(f"   Index: {entry_info.index}")
                print(f"   Num Hashes: {entry_info.num_hashes}")
                print(f"   Hash: {entry_info.hash.hex()}")
                print(f"   Executed Transaction Count: {entry_info.executed_transaction_count}")
                print(f"   Starting Transaction Index: {entry_info.starting_transaction_index}")
                print("---")
            else:
                print(f"⚠️  Received non-entry update: {response}")
                print("---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
