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

# Pump.fun program ID - we will subscribe to blocks containing its transactions
PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

async def main():
    """
    Main function that connects to Geyser and monitors blocks containing transactions
    for the specified pump.fun program.
    
    This will receive updates for any block that includes a transaction interacting
    with the PUMP_FUN_PROGRAM_ID.
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

        # Basic block subscription to filter by a specific program address
        request = geyser_pb2.SubscribeRequest(
            blocks={
                "blocks_filter": geyser_pb2.SubscribeRequestFilterBlocks(
                    account_include=[PUMP_FUN_PROGRAM_ID],
                    include_transactions=True,  # Include transactions in which the account is involved
                    include_accounts=False,     # Not allowed
                    include_entries=False       # Not allowed
                )
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )

        print(f"🚀 Starting block monitor for program: {PUMP_FUN_PROGRAM_ID}")
        print("📡 Listening for block updates...")
        print("---")

        update_count = 0
        async for response in stub.Subscribe(iter([request])):
            update_count += 1
            
            if response.block:
                block_info = response.block
                
                print(f"📦 Block Update #{update_count}")
                print(f"   Slot: {block_info.slot}")
                print(f"   Blockhash: {block_info.blockhash}")
                
                if block_info.transactions:
                    print(f"   Found {len(block_info.transactions)} transactions involving the program.")
                
                print("---")
            else:
                print(f"⚠️  Received non-block update: {response}")
                print("---")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
