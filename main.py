import asyncio
import os
import struct
import base58
import grpc
from dotenv import load_dotenv
from generated import geyser_pb2, geyser_pb2_grpc
from solders.pubkey import Pubkey

load_dotenv()

GEYSER_ENDPOINT = os.getenv("GEYSER_ENDPOINT")
GEYSER_API_TOKEN = os.getenv("GEYSER_API_TOKEN")
AUTH_TYPE = "x-token"  # or "basic"

PUMP_PROGRAM_ID = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
PUMP_CREATE_PREFIX = struct.pack("<Q", 8576854823835016728)

async def create_geyser_connection():
    """Establish a secure connection to the Geyser endpoint."""
    if AUTH_TYPE == "x-token":
        auth = grpc.metadata_call_credentials(
            lambda _, callback: callback((("x-token", GEYSER_API_TOKEN),), None)
        )
    else:  # Basic authentication
        auth = grpc.metadata_call_credentials(
            lambda _, callback: callback((("authorization", f"Basic {GEYSER_API_TOKEN}"),), None)
        )
    
    creds = grpc.composite_channel_credentials(grpc.ssl_channel_credentials(), auth)
    keepalive_options = [
        ('grpc.keepalive_time_ms', 30000),
        ('grpc.keepalive_timeout_ms', 10000),
        ('grpc.keepalive_permit_without_calls', True),
        ('grpc.http2.min_time_between_pings_ms', 10000),
    ]

    channel = grpc.aio.secure_channel(GEYSER_ENDPOINT, creds, options=keepalive_options)
    return geyser_pb2_grpc.GeyserStub(channel)


def create_subscription_request():
    """Create a subscription request for Pump.fun transactions."""
    request = geyser_pb2.SubscribeRequest()
    request.transactions["pump_filter"].account_include.append(str(PUMP_PROGRAM_ID))
    request.transactions["pump_filter"].failed = False
    request.commitment = geyser_pb2.CommitmentLevel.PROCESSED
    return request


def decode_create_instruction(ix_data: bytes, keys, accounts) -> dict:
    """Decode a create instruction from transaction data."""
    offset = 8  # Skip the 8-byte discriminator
    
    def get_account_key(index):
        """Extract account public key by index."""
        if index >= len(accounts):
            return "N/A"
        account_index = accounts[index]
        return base58.b58encode(keys[account_index]).decode()
    
    def read_string():
        """Read length-prefixed string from instruction data."""
        nonlocal offset
        length = struct.unpack_from("<I", ix_data, offset)[0]  # Read 4-byte length
        offset += 4
        value = ix_data[offset:offset + length].decode()       # Read string data
        offset += length
        return value
    
    def read_pubkey():
        """Read 32-byte public key from instruction data."""
        nonlocal offset
        value = base58.b58encode(ix_data[offset:offset + 32]).decode()
        offset += 32
        return value
    
    # Parse instruction data according to pump.fun's create schema
    name = read_string()
    symbol = read_string() 
    uri = read_string()
    creator = read_pubkey()
    
    return {
        "name": name,
        "symbol": symbol,
        "uri": uri,
        "creator": creator,
        "mint": get_account_key(0),           # New token mint address
        "bonding_curve": get_account_key(2),  # Price discovery mechanism
        "associated_bonding_curve": get_account_key(3),  # Token account for curve
        "user": get_account_key(7),           # Transaction signer
    }


def print_token_info(info, signature):
    """Print formatted token information."""
    print("\n🎯 New Pump.fun token detected!")
    print(f"Name: {info['name']} | Symbol: {info['symbol']}")
    print(f"Mint: {info['mint']}")
    print(f"Bonding curve: {info['bonding_curve']}")
    print(f"Associated bonding curve: {info['associated_bonding_curve']}")
    print(f"Creator: {info['creator']}")
    print(f"Signature: {signature}")


async def monitor_pump():
    """Monitor Solana blockchain for new Pump.fun token creations."""
    print(f"Starting Pump.fun token monitor using {AUTH_TYPE.upper()} authentication")
    stub = await create_geyser_connection()
    request = create_subscription_request()
    
    async for update in stub.Subscribe(iter([request])):
        # Only process transaction updates
        if not update.HasField("transaction"):
            continue
        
        tx = update.transaction.transaction.transaction
        msg = getattr(tx, "message", None)
        if msg is None:
            continue
        
        # Check each instruction in the transaction
        for ix in msg.instructions:
            # Quick check: is this a pump.fun create instruction?
            if not ix.data.startswith(PUMP_CREATE_PREFIX):
                continue

            # Decode and display token information
            info = decode_create_instruction(ix.data, msg.account_keys, ix.accounts)
            signature = base58.b58encode(bytes(update.transaction.transaction.signature)).decode()
            print_token_info(info, signature)


if __name__ == "__main__":
    asyncio.run(monitor_pump())
