import asyncio
import os
import sys
import grpc
import base58
import struct
import math
from typing import Optional, Dict, Any
from decimal import Decimal, getcontext

from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from generated import geyser_pb2, geyser_pb2_grpc

load_dotenv()

GEYSER_ENDPOINT = os.getenv("GEYSER_ENDPOINT")
GEYSER_API_TOKEN = os.getenv("GEYSER_API_TOKEN")

getcontext().prec = 50

MARKET_ADDRESS = "2wdankH7beNiLB5zJ2yCq9SnFFxQhDH3m1c4DurfqPvS" # Example address
SIGNIFICANT_PRICE_CHANGE_PCT = 0.001
FORCE_PRINT_EVERY_N_UPDATES = 500
MIN_BIN_MOVEMENT = 1

# Add tokens here as needed
SPL_TOKEN_SYMBOLS = {
    "So11111111111111111111111111111111111111112": "SOL",
    # Add more as needed!
}


def get_token_symbol(mint):
    return SPL_TOKEN_SYMBOLS.get(mint, mint[:6] + "..." + mint[-4:])


def calculate_dlmm_price_actual(active_id: int, bin_step: int) -> float:
    """
    Calculate the actual price for Meteora DLMM.
    Formula: price = (1 + bin_step/10000)^active_id
    """
    try:
        bin_step_decimal = bin_step / 10000.0
        base = 1.0 + bin_step_decimal
        if active_id == 0:
            return 1.0
        # For reasonable exponents
        if abs(active_id) <= 500:
            try:
                return base**active_id / 10 ** (
                    9 - 6
                )  # Adjust for WSOL and token decimals
            except OverflowError:
                pass
        log_base = math.log(base)
        log_result = active_id * log_base
        if log_result > 700:
            return float("inf")
        elif log_result < -700:
            return 0.0
        else:
            return math.exp(log_result)
    except Exception as e:
        print(f"⚠️  Error calculating DLMM price: {e}")
        return 1.0


def calculate_precise_price_decimal(active_id: int, bin_step: int) -> str:
    try:
        bin_step_decimal = Decimal(bin_step) / Decimal(10000)
        base = Decimal(1) + bin_step_decimal
        if active_id == 0:
            return "1.0"
        try:
            result = base**active_id / 10 ** (
                9 - 6
            )  # Adjust for WSOL and token decimals
            return str(result)
        except:
            ln_base = base.ln()
            ln_result = Decimal(active_id) * ln_base
            if ln_result > Decimal(230):
                return "inf"
            elif ln_result < Decimal(-230):
                return "~0"
            else:
                return str(ln_result.exp())
    except Exception as e:
        print(f"⚠️  Error in decimal price calculation: {e}")
        return "1.0"


def should_print_update(
    current_price: float,
    last_price: Optional[float],
    active_id: int,
    last_active_id: Optional[int],
    update_count: int,
    last_printed_update: int,
) -> tuple[bool, str]:
    reasons = []
    if last_price is None:
        return True, "First update"
    if update_count - last_printed_update >= FORCE_PRINT_EVERY_N_UPDATES:
        reasons.append(
            f"Periodic update ({update_count - last_printed_update} updates since last)"
        )
    if (
        current_price not in [float("inf"), 0.0]
        and last_price not in [float("inf"), 0.0]
        and last_price != 0
    ):
        price_change_pct = abs((current_price - last_price) / last_price) * 100
        if price_change_pct >= SIGNIFICANT_PRICE_CHANGE_PCT:
            reasons.append(f"Price change: {price_change_pct:.4f}%")
    if last_active_id is not None and active_id != last_active_id:
        bin_change = abs(active_id - last_active_id)
        if bin_change >= MIN_BIN_MOVEMENT:
            reasons.append(f"Bin movement: {bin_change} bins")
    if current_price in [float("inf"), 0.0] and last_price not in [float("inf"), 0.0]:
        reasons.append("Price became infinite/zero")
    if last_price in [float("inf"), 0.0] and current_price not in [float("inf"), 0.0]:
        reasons.append("Price recovered from infinite/zero")
    if reasons:
        return True, " | ".join(reasons)
    else:
        return False, "No significant change"


def parse_static_parameters(data: bytes, offset: int) -> tuple[Dict[str, Any], int]:
    params = {}
    params["base_factor"] = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    params["filter_period"] = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    params["decay_period"] = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    params["reduction_factor"] = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    params["variable_fee_control"] = struct.unpack("<I", data[offset : offset + 4])[0]
    offset += 4
    params["max_volatility_accumulator"] = struct.unpack(
        "<I", data[offset : offset + 4]
    )[0]
    offset += 4
    params["min_bin_id"] = struct.unpack("<i", data[offset : offset + 4])[0]
    offset += 4
    params["max_bin_id"] = struct.unpack("<i", data[offset : offset + 4])[0]
    offset += 4
    params["protocol_share"] = struct.unpack("<H", data[offset : offset + 2])[0]
    offset += 2
    params["base_fee_power_factor"] = struct.unpack("<B", data[offset : offset + 1])[0]
    offset += 1
    offset += 5
    return params, offset


def parse_variable_parameters(data: bytes, offset: int) -> tuple[Dict[str, Any], int]:
    params = {}
    params["volatility_accumulator"] = struct.unpack("<I", data[offset : offset + 4])[0]
    offset += 4
    params["volatility_reference"] = struct.unpack("<I", data[offset : offset + 4])[0]
    offset += 4
    params["index_reference"] = struct.unpack("<i", data[offset : offset + 4])[0]
    offset += 4
    offset += 4
    params["last_update_timestamp"] = struct.unpack("<q", data[offset : offset + 8])[0]
    offset += 8
    offset += 8
    return params, offset


def parse_protocol_fee(data: bytes, offset: int) -> tuple[Dict[str, Any], int]:
    protocol_fee = {}
    protocol_fee["amount_x"] = struct.unpack("<Q", data[offset : offset + 8])[0]
    offset += 8
    protocol_fee["amount_y"] = struct.unpack("<Q", data[offset : offset + 8])[0]
    offset += 8
    return protocol_fee, offset


def parse_meteora_dlmm_account_data(data: bytes) -> Optional[Dict[str, Any]]:
    try:
        if len(data) < 500:
            return None
        pool_data = {}
        offset = 8
        static_params, offset = parse_static_parameters(data, offset)
        pool_data["static_parameters"] = static_params
        variable_params, offset = parse_variable_parameters(data, offset)
        pool_data["variable_parameters"] = variable_params
        if len(data) < offset + 50:
            return None
        pool_data["bump_seed"] = struct.unpack("<B", data[offset : offset + 1])[0]
        offset += 1
        pool_data["bin_step_seed"] = struct.unpack("<H", data[offset : offset + 2])[0]
        offset += 2
        pool_data["pair_type"] = struct.unpack("<B", data[offset : offset + 1])[0]
        offset += 1
        pool_data["active_id"] = struct.unpack("<i", data[offset : offset + 4])[0]
        offset += 4
        pool_data["bin_step"] = struct.unpack("<H", data[offset : offset + 2])[0]
        offset += 2
        pool_data["status"] = struct.unpack("<B", data[offset : offset + 1])[0]
        offset += 1
        pool_data["require_base_factor_seed"] = struct.unpack(
            "<B", data[offset : offset + 1]
        )[0]
        offset += 1
        pool_data["base_factor_seed"] = struct.unpack("<H", data[offset : offset + 2])[
            0
        ]
        offset += 2
        pool_data["activation_type"] = struct.unpack("<B", data[offset : offset + 1])[0]
        offset += 1
        pool_data["creator_pool_on_off_control"] = struct.unpack(
            "<B", data[offset : offset + 1]
        )[0]
        offset += 1
        pool_data["token_x_mint"] = base58.b58encode(
            data[offset : offset + 32]
        ).decode()
        offset += 32
        pool_data["token_y_mint"] = base58.b58encode(
            data[offset : offset + 32]
        ).decode()
        offset += 32
        pool_data["reserve_x"] = base58.b58encode(data[offset : offset + 32]).decode()
        offset += 32
        pool_data["reserve_y"] = base58.b58encode(data[offset : offset + 32]).decode()
        offset += 32
        if len(data) >= offset + 16:
            protocol_fee, offset = parse_protocol_fee(data, offset)
            pool_data["protocol_fee"] = protocol_fee
        return pool_data
    except Exception as e:
        return None


def format_account_address(pubkey_data) -> str:
    try:
        if isinstance(pubkey_data, bytes):
            return base58.b58encode(pubkey_data).decode("utf-8")
        elif isinstance(pubkey_data, str):
            return pubkey_data
        else:
            return str(pubkey_data)
    except Exception as e:
        return f"<invalid_pubkey: {e}>"


def format_price_display(price: float, decimals: int = 12) -> str:
    if price == float("inf"):
        return "∞"
    elif price == 0.0:
        return "0"
    elif price < 1e-15:
        return f"{price:.2e}"
    elif price > 1e15:
        return f"{price:.2e}"
    else:
        if price >= 1:
            return f"{price:,.{decimals}f}".rstrip("0").rstrip(".")
        else:
            return f"{price:.{decimals}f}".rstrip("0").rstrip(".")


async def monitor_meteora_pool_price(market_address: str):
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
        request = geyser_pb2.SubscribeRequest(
            accounts={
                "accounts_filter": geyser_pb2.SubscribeRequestFilterAccounts(
                    account=[market_address],
                )
            },
            commitment=geyser_pb2.CommitmentLevel.PROCESSED,
        )
        print(f"🚀 Meteora DLMM Smart Price Monitor")
        print(f"📍 Pool Address: {market_address}")
        print(f"🔍 Filtering Rules:")
        print(f"   • Price change ≥ {SIGNIFICANT_PRICE_CHANGE_PCT}%")
        print(f"   • Bin movement ≥ {MIN_BIN_MOVEMENT} bins")
        print(f"   • Force update every {FORCE_PRINT_EVERY_N_UPDATES} updates")
        print("📡 Monitoring for significant changes...")
        print("=" * 100)
        update_count = 0
        printed_count = 0
        last_printed_update = 0
        last_price = None
        last_active_id = None
        skipped_count = 0

        async for response in stub.Subscribe(iter([request])):
            if response.account:
                update_count += 1
                account_info = response.account
                if account_info.account.data:
                    pool_data = parse_meteora_dlmm_account_data(
                        account_info.account.data
                    )
                    if (
                        pool_data
                        and "active_id" in pool_data
                        and "bin_step" in pool_data
                    ):
                        active_id = pool_data["active_id"]
                        bin_step = pool_data["bin_step"]
                        current_price = calculate_dlmm_price_actual(active_id, bin_step)
                        should_print, reason = should_print_update(
                            current_price,
                            last_price,
                            active_id,
                            last_active_id,
                            update_count,
                            last_printed_update,
                        )
                        if should_print:
                            printed_count += 1
                            last_printed_update = update_count
                            account_pubkey = format_account_address(
                                account_info.account.pubkey
                            )
                            print(
                                f"\n🎯 Update #{printed_count} (Total: {update_count:,}) | Slot: {account_info.slot:,}"
                            )
                            print(f"📋 Reason: {reason}")
                            if skipped_count > 0:
                                print(
                                    f"⏭️  Skipped {skipped_count} updates with no significant changes"
                                )
                                skipped_count = 0
                            print(f"📮 Account: {account_pubkey}")
                            print(f"\n🎯 DLMM Pool State:")
                            print(f"   Active Bin ID: {active_id:,}")
                            print(
                                f"   Bin Step: {bin_step} bps ({bin_step / 100:.2f}%)"
                            )
                            # Symbol mapping
                            mint_x = pool_data.get("token_x_mint", "")
                            mint_y = pool_data.get("token_y_mint", "")
                            sym_x = get_token_symbol(mint_x)
                            sym_y = get_token_symbol(mint_y)
                            print(f"\n🪙 Token Pair:")
                            print(f"   Token X (Base): {sym_x} [{mint_x}]")
                            print(f"   Token Y (Quote): {sym_y} [{mint_y}]")
                            # High precision price
                            precise_price = calculate_precise_price_decimal(
                                active_id, bin_step
                            )
                            # Detect SOL side
                            sol_mint = "So11111111111111111111111111111111111111112"
                            showline = ""
                            if mint_x == sol_mint:
                                showline = f"💰 1 {sym_y} = {format_price_display(current_price)} SOL"
                            elif mint_y == sol_mint:
                                if current_price == 0:
                                    showline = f"💰 1 {sym_x} = ∞ SOL"
                                else:
                                    showline = f"💰 1 {sym_x} = {format_price_display(1 / current_price)} SOL"
                            else:
                                showline = f"💰 1 {sym_y} = {format_price_display(current_price)} {sym_x}"
                            print(f"\n{showline}")
                            if precise_price not in ["inf", "~0"]:
                                print(f"   High Precision: {precise_price}")
                            print(
                                f"\n🧮 Formula: (1 + {bin_step}/10000)^{active_id} = {1 + bin_step / 10000:.8f}^{active_id}"
                            )
                            # Calculate and show changes
                            if (
                                last_price is not None
                                and current_price not in [float("inf"), 0.0]
                                and last_price not in [float("inf"), 0.0]
                            ):
                                price_change = current_price - last_price
                                price_change_pct = (price_change / last_price) * 100
                                direction = "📈" if price_change > 0 else "📉"
                                print(f"\n📊 Changes Since Last Update:")
                                print(
                                    f"   Price: {direction} {format_price_display(abs(price_change))} ({price_change_pct:+.6f}%)"
                                )
                            # Show bin movement
                            if (
                                last_active_id is not None
                                and last_active_id != active_id
                            ):
                                bin_change = active_id - last_active_id
                                direction = "⬆️" if bin_change > 0 else "⬇️"
                                print(
                                    f"   Bins: {direction} {bin_change:+} bins (from {last_active_id:,} to {active_id:,})"
                                )
                            # Show protocol fees if significant
                            protocol_fee = pool_data.get("protocol_fee", {})
                            if protocol_fee and (
                                protocol_fee.get("amount_x", 0) > 0
                                or protocol_fee.get("amount_y", 0) > 0
                            ):
                                print(f"\n💸 Protocol Fees:")
                                print(f"   X: {protocol_fee.get('amount_x', 0):,}")
                                print(f"   Y: {protocol_fee.get('amount_y', 0):,}")
                            print("-" * 100)
                        else:
                            skipped_count += 1
                            if skipped_count % 50 == 0:
                                print(
                                    f"⏸️  Monitoring... {skipped_count} updates skipped (Update #{update_count:,})"
                                )
                        if current_price not in [float("inf"), 0.0]:
                            last_price = current_price
                        last_active_id = active_id


async def main():
    if not GEYSER_ENDPOINT or not GEYSER_API_TOKEN:
        print("❌ Missing environment variables")
        sys.exit(1)
    try:
        decoded = base58.b58decode(MARKET_ADDRESS)
        if len(decoded) != 32:
            raise ValueError("Invalid address length")
        print(f"✅ Valid address: {MARKET_ADDRESS}")
    except Exception as e:
        print(f"❌ Invalid address: {e}")
        sys.exit(1)
    # Test the price calculation with example data
    print(f"\n🧪 Testing Price Calculation:")
    print(f"   Example: activeId=-47, binStep=100")
    test_price = calculate_dlmm_price_actual(-47, 100)
    print(f"   Result: {test_price:.8f}")
    print()
    print(f"🔧 Filter Settings (you can modify these at the top of the file):")
    print(f"   SIGNIFICANT_PRICE_CHANGE_PCT = {SIGNIFICANT_PRICE_CHANGE_PCT}%")
    print(f"   MIN_BIN_MOVEMENT = {MIN_BIN_MOVEMENT}")
    print(f"   FORCE_PRINT_EVERY_N_UPDATES = {FORCE_PRINT_EVERY_N_UPDATES}")
    print()
    await monitor_meteora_pool_price(MARKET_ADDRESS)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Monitor stopped by user")
        print("📊 Final stats will be shown above")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
