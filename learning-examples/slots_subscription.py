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
    Main function that connects to Geyser and subscribes to basic slot updates.

    This provides a stream of slot updates as they are processed by the validator.
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

        # Basic slot subscription
        request = geyser_pb2.SubscribeRequest(
            slots={
                "slots_filter": geyser_pb2.SubscribeRequestFilterSlots(
                    filter_by_commitment=True,  # Filter by commitment level, if False - slots for all commitment levels will be returned
                    interslot_updates=False,  # Stream slot construction progress, not just when commitment is reached
                )
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )

        print("🚀 Starting basic slot monitor...")
        print("📡 Listening for slot updates...")
        print("---")

        update_count = 0
        async for response in stub.Subscribe(iter([request])):
            update_count += 1

            if response.slot:
                slot_info = response.slot

                print(f"🎰 Slot Update #{update_count}")
                print(f"   Slot: {slot_info.slot}")
                print(f"   Parent: {slot_info.parent}")
                print(f"   Status: {geyser_pb2.SlotStatus.Name(slot_info.status)}")
                print(
                    f"   Dead error: {slot_info.dead_error}"
                )  # Reason why this slot failed/died (e.g. "TooManyShreds", "InvalidParent")
                print("---")
            else:
                print(f"⚠️  Received non-slot update: {response}")
                print("---")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Stopping monitor...")
    except Exception as e:
        print(f"❌ Error: {e}")
