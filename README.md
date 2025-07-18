## Introduction to Geyser plugin

There are multiple ways for listening to updates in Solana blockchain. The default method is to use WebSocket methods. However, they have certain limitations.

`blockSubscribe` is considered unstable and may not be supported by all RPC providers. Moreover, this method doesn't support `processed` commitment level. It waits for complete blocks to be confirmed or finalized before sending data.

`logsSubscribe` is faster than `blockSubscribe` since it streams logs in real-time as transactions are processed. Its limitation is that it truncates log messages that exceed size limits. If you need complete transaction data, you still need to use `blockSubscribe` or send additional RPC calls.

Luckily, a plugin mechanism has been introduced to Solana nodes. They have been enhanced to support a Geyser plugin mechanism which is a special interface that allows RPC providers to stream information about accounts, slots, blocks, and transactions to external data stores.

There are Geyser plugins for data storage (e.g., PostgreSQL, Google Bigtable), real-time streaming (gRPC, WebSocket plugins) and [other purposes](https://github.com/rpcpool/solana-geyser-park).

## Yellowstone gRPC plugin implementation

In this tutorial, we focus on the gRPC plugin which uses the [gRPC](https://grpc.io/docs/what-is-grpc/introduction/) protocol as a channel for transmitting Solana updates. Its most popular implementation is done by the Triton One team within the Project Yellowstone, hence the name is Yellowstone gRPC or Geyser gRPC.

By default, gRPC uses [protocol buffers](https://developers.google.com/protocol-buffers) as the Interface Definition Language (IDL) for describing both the service interface and the structure of the messages. For a user of Yellowstone gRPC plugin, it means that there are special proto files based on which client code will be generated and imported into other modules.

Those [proto files](https://github.com/rpcpool/yellowstone-grpc/tree/master/yellowstone-grpc-proto/proto) define the service interface (what methods are available), message structures (request/response formats), data types, and enums. These definitions support code generation for all popular programming languages including Python, Go, Java, C++, JavaScript/Node.js, Rust, C#, and many others. A few examples below show the service interface and message structures defined in the proto files.

```protobuf
// Service interface definition
service Geyser {
  rpc Subscribe(stream SubscribeRequest) returns (stream SubscribeUpdate);
  rpc Ping(PingRequest) returns (PongResponse);
  rpc GetLatestBlockhash(GetLatestBlockhashRequest) returns (GetLatestBlockhashResponse);
}

// Message structures definition
message SubscribeRequest {
  map<string, SubscribeRequestFilterAccounts> accounts = 1;
  map<string, SubscribeRequestFilterSlots> slots = 2;
  CommitmentLevel commitment = 4;
  bool ping = 6;
}

// Data types and enums definition
enum CommitmentLevel {
  PROCESSED = 0;
  CONFIRMED = 1;
  FINALIZED = 2;
}

message SubscribeRequestFilterAccounts {
  repeated string account = 1;
  repeated string owner = 2;
}
```

Client code is generated based on proto files using the protoc compiler (a part of [grpc tools](https://grpc.io/)). The compiler generates service stubs (client interfaces), message classes for data structures, and type definitions specific to the target programming language.

```bash
# Generate Python client code
python -m grpc_tools.protoc \
    --python_out=./generated \
    --grpc_python_out=./generated \
    --proto_path=./proto \
    geyser.proto solana-storage.proto
```

The generated client code handles all the low-level complexity: serialization and deserialization between binary protobuf format and language-specific objects, network communication over HTTP/2, type safety enforcement, and message validation.

## Practice: listening to new tokens minted on PumpFun

Let's build a real-time token monitor that detects new pump.fun tokens the moment they're created. We'll construct this step-by-step.

For package management, we will use super fast and modern [uv](https://docs.astral.sh/uv/getting-started/installation/) tool.

*If you are in a hurry, simply clone this repository and sync dependencies*.

```bash
git clone https://github.com/chainstacklabs/grpc-geyser-tutorial .
uv sync
```

### Step 1: Project setup and dependencies

First, we need to install the required packages:

```bash
uv init
uv add grpcio grpcio-tools base58 solders python-dotenv
```

**Why these specific packages?**

- `grpcio`: core gRPC library for Python.
- `grpcio-tools`: contains protoc compiler for generating Python code from .proto files.
- `base58`: Solana addresses use Base58 encoding, not standard Base64.
- `solders`: Rust-based Solana library for Python, much faster than `solana-py`.
- `python-dotenv`: manages environment variables safely.

### Step 2: Generate gRPC client code

Download the official Yellowstone proto files and generate Python client code:

```bash
# Create folders for files to be downloaded and generated code
mkdir proto
mkdir generated

# Download proto files
curl -o proto/geyser.proto https://raw.githubusercontent.com/rpcpool/yellowstone-grpc/master/yellowstone-grpc-proto/proto/geyser.proto

curl -o proto/solana-storage.proto https://raw.githubusercontent.com/rpcpool/yellowstone-grpc/master/yellowstone-grpc-proto/proto/solana-storage.proto

# Generate Python client code with uv
uv run --with grpcio-tools -- python -m grpc_tools.protoc \
    --python_out=./generated \
    --grpc_python_out=./generated \
    --proto_path=./proto \
    geyser.proto solana-storage.proto
```

**What happens here?** The protocol buffer compiler (protoc) compiler reads the `.proto` files (which define the gRPC service interface) and generates Python classes that handle all the networking, serialization, and type safety automatically.

The protoc generates the code with absolute imports. Since we placed the generated files to the `generated` folder, we need to fix imports to avoid errors during the further steps:

1. In `geyser_pb2.py`:
	- Change from `import solana_storage_pb2 as solana__storage__pb2` to `from . import solana_storage_pb2 as solana__storage__pb2`.
	- Change from `from solana_storage_pb2 import *` to `from .solana_storage_pb2 import *`.

2. In `geyser_pb2_grpc.py`:
	- Change from `import geyser_pb2 as geyser__pb2` to `from . import geyser_pb2 as geyser__pb2`.

### Step 3: Environment configuration

Create a `.env` file with your Geyser credentials. If you use Chainstack, enable the Yellowstone gRPC Geyser Plugin and the credentials will appear on the overview page of your Solana node.

```env
GEYSER_ENDPOINT=YOUR_CHAINSTACK_YELLOWSTONE_GEYSER_GRPC_ENDPOINT
GEYSER_API_TOKEN=YOUR_CHAINSTACK_YELLOWSTONE_GEYSER_X_TOKEN
```
See also [Chainstack Yellowstone Geyser add-on](https://chainstack.com/marketplace/yellowstone-grpc-geyser-plugin/).

### Step 4: Core constants and setup

```python
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
```

**Why these specific values?**

- `PUMP_PROGRAM_ID`: this is pump.fun's program address on Solana mainnet.
- `PUMP_CREATE_PREFIX`: this is the 8-byte discriminator for pump.fun's "create" instruction. Every instruction type has a unique discriminator calculated from its name hash.

**How discriminators work:** Solana programs use the first 8 bytes of instruction data to identify which function to call. Please check a more detailed example [here](https://github.com/chainstacklabs/pump-fun-bot/tree/main/learning-examples).

### Step 5: gRPC connection management

```python
async def create_geyser_connection():
    """Establish a secure connection to the Geyser endpoint."""
    if AUTH_TYPE == "x-token":
        auth = grpc.metadata_call_credentials(
            lambda _, callback: callback((("x-token", GEYSER_API_TOKEN),), None)
        )
    else:  # Basic authentication
        auth = grpc.metadata_call_credentials(
            lambda _, callback: callback(
                (("authorization", f"Basic {GEYSER_API_TOKEN}"),), None
            )
        )

    creds = grpc.composite_channel_credentials(grpc.ssl_channel_credentials(), auth)
    # We can add keepalive options to maintain the connection
    # This helps prevent the connection from being closed during periods of inactivity
    keepalive_options = [
        ("grpc.keepalive_time_ms", 30000),
        ("grpc.keepalive_timeout_ms", 10000),
        ("grpc.keepalive_permit_without_calls", True),
        ("grpc.http2.min_time_between_pings_ms", 10000),
    ]

    channel = grpc.aio.secure_channel(GEYSER_ENDPOINT, creds, options=keepalive_options)
    return geyser_pb2_grpc.GeyserStub(channel)
```

### Step 6: Subscription configuration

```python
def create_subscription_request():
    """Create a subscription request for Pump.fun transactions."""
    request = geyser_pb2.SubscribeRequest()
    request.transactions["pump_filter"].account_include.append(str(PUMP_PROGRAM_ID))
    request.transactions["pump_filter"].failed = False
    request.commitment = geyser_pb2.CommitmentLevel.PROCESSED
    return request
```

**Understanding the filter configuration:**
- `account_include`: only stream transactions that interact with pump.fun program.
- `failed = False`: exclude failed transactions to reduce noise.
- `PROCESSED` commitment: get updates as soon as transactions are processed (fastest possible).

### Step 7: Instruction data decoding

This is where the magic happens - extracting meaningful data from raw blockchain bytes:

```python
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
```

**Understanding the data structure:**
- **Length-prefixed strings**: Solana stores strings as `[4-byte length][string data]`
- **Account indices**: instructions reference accounts by index to save space
- **Fixed positions**: pump.fun's create instruction always puts specific accounts at predictable indices

**Why this parsing approach?** Instruction data is just raw bytes. We need to know the exact data layout (schema) to extract meaningful information. This schema knowledge comes from analyzing [pump.fun's IDL files](https://github.com/pump-fun/pump-public-docs/tree/main/idl).

### Step 8: Main monitoring loop

```python
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
```

**Why check the discriminator first?** This 8-byte comparison is extremely fast and eliminates 99.9% of irrelevant instructions before attempting parsing.

### Step 9: Running the monitor

```python
if __name__ == "__main__":
    asyncio.run(monitor_pump())
```

To run the code, execute the following command in your terminal:

```bash
uv run main.py
```

## Other learning examples

Here are short summaries of each learning example file, from basic to advanced, for each group of filters.

### Account filters

- **`accounts_basic_filter.py`**: this example demonstrates how to subscribe to updates for a single, specific account. It's the simplest way to monitor changes to a particular address (e.g., reserve changes in a bonding curve account or AMM pool).
- **`accounts_advanced_filter.py`**: this script shows a more advanced use case, subscribing to accounts based on the program that owns them and a data discriminator. This is useful for tracking all accounts of a certain type created by a specific program (e.g., reserve changes in all active bonding curves or certain AMM pools).

### Transaction filters

- **`transactions_basic_filter.py`**: this example shows how to subscribe to all successful transactions that interact with a specific account. It's a good starting point for tracking activity related to a particular address.
- **`transactions_advanced_filter.py`**: this script demonstrates more complex filtering for transactions containing all required programs (e.g, for detecting arbitrage transactions).

### Other subscriptions

- **`slots_subscription.py`**: this example shows how to subscribe to slot updates, giving you a real-time feed of when new slots are processed by the validator.
- **`blocks_subscription.py`**: this script demonstrates how to subscribe to entire blocks that contain transactions interacting with a specific account.
- **`blocks_meta_subscription.py`**: this example shows how to subscribe to just the metadata of blocks, which is a lightweight way to track block production.
- **`entries_subscription.py`**: this script demonstrates how to subscribe to ledger entries, which provides a low-level stream of the changes being written to the Solana ledger.
- **`transaction_statuses_subscription.py`**: this example shows how to subscribe to the status of transactions, allowing you to track them from processing to finalization.

### Advanced examples

- **`meteora_dlmm_monitor.py`**: this is a more complex, real-world example that monitors a Meteora Dynamic Liquidity Market Maker (DLMM). It demonstrates how to decode complex account data and track price changes in a DLMM pool.


