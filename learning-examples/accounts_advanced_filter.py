import asyncio
import os
import sys
import grpc
import hashlib
import base58

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
from generated import geyser_pb2, geyser_pb2_grpc

load_dotenv()


GEYSER_ENDPOINT = os.getenv("GEYSER_ENDPOINT")
GEYSER_API_TOKEN = os.getenv("GEYSER_API_TOKEN")

# Pump.fun program ID - this is the main program that manages all pump.fun tokens
PUMP_FUN_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


def calculate_discriminator(account_name: str) -> int:
    """
    Calculate the 8-byte discriminator for an Anchor account type.

    The discriminator is the first 8 bytes of SHA-256 hash of "account:{account_name}"
    This is used to identify different types of accounts in Anchor programs.

    Args:
        account_name: The name of the account struct (e.g., "BondingCurve")

    Returns:
        The discriminator as a little-endian integer
    """
    hash_input = f"account:{account_name}"
    hash_result = hashlib.sha256(hash_input.encode()).digest()
    discriminator_bytes = hash_result[:8]
    return int.from_bytes(discriminator_bytes, "little")


# Calculate the bonding curve discriminator
BONDING_CURVE_DISCRIMINATOR = calculate_discriminator("BondingCurve")
print(f"Bonding Curve Discriminator: {BONDING_CURVE_DISCRIMINATOR}")


async def main():
    """
    Main function that connects to Geyser and monitors pump.fun bonding curve updates.

    This will receive updates for:
    - New token creation (when bonding curves are created)
    - Trading activity (buys/sells that change bonding curve state)
    - Token progression through the bonding curve
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
        # Create the gRPC stub for making requests
        stub = geyser_pb2_grpc.GeyserStub(channel)

        # Create subscription request to monitor pump.fun bonding curve accounts
        request = geyser_pb2.SubscribeRequest(
            accounts={
                "accounts_filter": geyser_pb2.SubscribeRequestFilterAccounts(
                    owner=[PUMP_FUN_PROGRAM_ID],
                    filters=[
                        # This ensures we only get bonding curve accounts, not other pump.fun accounts
                        geyser_pb2.SubscribeRequestFilterAccountsFilter(
                            memcmp=geyser_pb2.SubscribeRequestFilterAccountsFilterMemcmp(
                                offset=0,  # Discriminator is at the beginning of account data
                                bytes=BONDING_CURVE_DISCRIMINATOR.to_bytes(8, "little"),
                            )
                        ),
                    ],
                )
            },
            # Use PROCESSED commitment for faster updates (vs CONFIRMED or FINALIZED)
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )

        print("🚀 Starting pump.fun bonding curve monitor...")
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

                # You can decode the bonding curve data here to get:
                # - Virtual SOL reserves
                # - Virtual token reserves
                # - Real token reserves
                # - Token mint address
                # - Bonding curve progress

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
