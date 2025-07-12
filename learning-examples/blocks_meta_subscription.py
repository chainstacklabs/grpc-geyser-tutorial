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
    Main function that connects to Geyser and monitors block metadata for all blocks.
    
    This will receive metadata for every block processed by the Geyser node.
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

        # Basic blocks_meta subscription for all blocks
        request = geyser_pb2.SubscribeRequest(
            blocks_meta={
                "blocks_meta_filter": geyser_pb2.SubscribeRequestFilterBlocksMeta() # Don't have filters
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )

        print("🚀 Starting block metadata monitor for all blocks...")
        print("📡 Listening for block metadata updates...")
        print("---")

        update_count = 0
        async for response in stub.Subscribe(iter([request])):
            update_count += 1
            
            if response.block_meta:
                block_meta_info = response.block_meta
                
                print(f"📦 Block Meta Update #{update_count}")
                print(f"   Slot: {block_meta_info.slot}")
                print(f"   Blockhash: {block_meta_info.blockhash}")
                print(f"   Parent Slot: {block_meta_info.parent_slot}")
                print(f"   Block Time: {block_meta_info.block_time.timestamp}")
                print(f"   Transaction Count: {block_meta_info.executed_transaction_count}")
                print("---")
            else:
                print(f"⚠️  Received non-block_meta update: {response}")
                print("---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
