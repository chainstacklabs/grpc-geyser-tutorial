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
    Demonstrates using the from_slot parameter to recover slots missed during a
    brief disconnect.

    from_slot starts the stream from a past slot instead of the current slot, so
    a client that briefly drops its connection can reconnect and replay the gap
    without missing events.

    It is a reconnection-recovery mechanism, NOT a historical backfill. The
    server keeps only a small ring buffer of recent slots (roughly the last ~100
    slots, about a minute, on shared nodes). Requesting a from_slot older than
    the buffer returns OUT_OF_RANGE with the oldest available slot. Dedicated
    nodes can be configured with a larger buffer.

    For arbitrary historical data, use the JSON-RPC methods (getBlock,
    getSignaturesForAddress, getTransaction) instead of from_slot.
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

        # First, get the current slot by subscribing briefly
        print("📍 Getting current network slot...")
        current_slot = None

        try:
            # Try Ping first
            ping_request = geyser_pb2.PingRequest()
            ping_response = await stub.Ping(ping_request)
            current_slot = ping_response.slot
            print(f"   Current slot from Ping: {current_slot}")
        except Exception:
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

        # Start within the replay buffer. The buffer is small (~100 slots on
        # shared nodes), so use a conservative offset. Older than the buffer
        # returns OUT_OF_RANGE — for real history use JSON-RPC, not from_slot.
        slots_back = 100  # conservative; within the ~100-slot shared-node buffer
        from_slot = current_slot - slots_back

        print(f"⏰ Replaying from slot {from_slot} ({slots_back} slots back)")
        print(f"   That's roughly {slots_back * 0.4 / 60:.1f} minutes of recent slots")
        print("---")

        # Create subscription with from_slot to replay the recent gap
        request = geyser_pb2.SubscribeRequest(
            slots={
                "recover": geyser_pb2.SubscribeRequestFilterSlots(
                    filter_by_commitment=True,
                )
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
            from_slot=from_slot,  # replay from this recent slot
        )

        print("🚀 Replaying recent slots from the buffer...")
        print("📡 Catching up from the past slot to the current tip...")
        print("---")

        slot_count = 0
        first_slot = None

        try:
            async for response in stub.Subscribe(iter([request])):
                if response.slot:
                    slot_count += 1

                    if first_slot is None:
                        first_slot = response.slot.slot
                        print(f"✅ First replayed slot received: {first_slot}")

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
                        print("🎉 Caught up to current slot!")
                        print(f"   Replayed {slot_count} slots")
                        print(f"   From: {first_slot}")
                        print(f"   To: {response.slot.slot}")
                        break

        except grpc.RpcError as e:
            if "not available" in str(e.details()):
                # The requested slot fell outside the replay buffer
                import re
                match = re.search(r"last available: (\d+)", str(e.details()))
                if match:
                    oldest = int(match.group(1))
                    depth = current_slot - oldest
                    print(f"❌ Requested slot {from_slot} is outside the replay buffer")
                    print(f"   Oldest available slot: {oldest}")
                    print(f"   Buffer depth: ~{depth} slots (~{depth * 0.4 / 60:.1f} minutes)")
                    print("\n💡 from_slot only covers the recent buffer. For older data,")
                    print("   use JSON-RPC (getBlock / getSignaturesForAddress / getTransaction).")
            else:
                print(f"❌ Error: {e.code()} - {e.details()}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Replay stopped")
    except Exception as e:
        print(f"❌ Error: {e}")
