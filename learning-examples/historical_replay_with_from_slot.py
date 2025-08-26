import asyncio
import os
import sys
import grpc

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from generated import geyser_pb2, geyser_pb2_grpc

load_dotenv()

GEYSER_ENDPOINT = os.getenv("GEYSER_ENDPOINT")
GEYSER_API_TOKEN = os.getenv("GEYSER_API_TOKEN")


async def main():
    """
    Demonstrates using from_slot parameter for historical data replay.
    
    The from_slot parameter allows you to start streaming from a specific slot
    instead of the current slot. This is useful for:
    - Replaying historical data
    - Backfilling missed events
    - Testing with past blockchain data
    - Analyzing historical patterns
    
    Note: Typically only recent slots (within a few minutes/hours) are available.
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

        # First, try to get a current slot by subscribing briefly
        print("📍 Getting current network slot...")
        current_slot = None
        
        try:
            # Try Ping first
            ping_request = geyser_pb2.PingRequest()
            ping_response = await stub.Ping(ping_request)
            current_slot = ping_response.slot
            print(f"   Current slot from Ping: {current_slot}")
        except:
            # If Ping doesn't work, get it from a brief subscription
            temp_request = geyser_pb2.SubscribeRequest(
                slots={"temp": geyser_pb2.SubscribeRequestFilterSlots()},
                commitment=geyser_pb2.CommitmentLevel.PROCESSED,
            )
            async for response in stub.Subscribe(iter([temp_request])):
                if response.slot:
                    current_slot = response.slot.slot
                    print(f"   Current slot from stream: {current_slot}")
                    break
        
        if not current_slot:
            print("   ⚠️  Could not get current slot")
            return

        # Calculate a starting point - use a safe value within retention window
        # Each slot is ~400ms, so 100 slots = ~40 seconds
        slots_back = 100  # Conservative value that should always work
        from_slot = current_slot - slots_back
        
        print(f"⏰ Replaying from slot {from_slot} ({slots_back} slots back)")
        print(f"   This represents approximately {slots_back * 0.4 / 60:.1f} minutes of history")
        print("---")

        # Create subscription with from_slot parameter
        request = geyser_pb2.SubscribeRequest(
            slots={
                "historical": geyser_pb2.SubscribeRequestFilterSlots(
                    filter_by_commitment=True,
                )
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
            from_slot=from_slot  # Start from historical slot
        )

        print("🚀 Starting historical replay...")
        print("📡 Streaming slots from the past to present...")
        print("---")

        slot_count = 0
        first_slot = None
        
        try:
            async for response in stub.Subscribe(iter([request])):
                if response.slot:
                    slot_count += 1
                    
                    if first_slot is None:
                        first_slot = response.slot.slot
                        print(f"✅ First historical slot received: {first_slot}")
                    
                    # Show progress every 100 slots
                    if slot_count % 100 == 0:
                        current = response.slot.slot
                        progress = ((current - first_slot) / (current_slot - first_slot)) * 100
                        print(f"📊 Progress: {slot_count} slots processed")
                        print(f"   Current slot: {current}")
                        print(f"   Catching up: {progress:.1f}% complete")
                        print("---")
                    
                    # Stop after catching up to near-current
                    if response.slot.slot >= current_slot - 10:
                        print(f"🎉 Caught up to current slot!")
                        print(f"   Processed {slot_count} historical slots")
                        print(f"   From: {first_slot}")
                        print(f"   To: {response.slot.slot}")
                        break
                        
        except grpc.RpcError as e:
            if "not available" in str(e.details()):
                # Extract the oldest available slot from error message
                import re
                match = re.search(r"last available: (\d+)", str(e.details()))
                if match:
                    oldest = int(match.group(1))
                    print(f"❌ Requested slot {from_slot} is too old")
                    print(f"   Oldest available slot: {oldest}")
                    print(f"   That's {(current_slot - oldest) * 0.4 / 3600:.1f} hours of history")
                    print("\n💡 Tip: Try using a more recent from_slot value")
            else:
                print(f"❌ Error: {e.code()} - {e.details()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Historical replay stopped")
    except Exception as e:
        print(f"❌ Error: {e}")