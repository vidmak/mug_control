# ble_tool.py
# Simple BLE CLI for macOS using bleak
# - Scan and list devices
# - Connect and list services/characteristics (read values when allowed)
# - Write to a selected characteristic

import asyncio
from typing import Dict, Tuple, List
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

SCAN_SECONDS = 8


def printable_bytes(b: bytes, max_len: int = 64) -> str:
    """Show both hex and (best-effort) UTF-8 preview."""
    hex_part = b[:max_len].hex(" ")
    try:
        text = b.decode("utf-8")
        text_part = text if len(text) <= max_len else text[:max_len] + "…"
    except UnicodeDecodeError:
        text_part = "⟂"
    return f"hex[{hex_part}] | utf8[{text_part}]"


def ask_index(prompt: str, upper: int) -> int:
    while True:
        s = input(f"{prompt} [0-{upper-1}]: ").strip()
        if s.isdigit():
            i = int(s)
            if 0 <= i < upper:
                return i
        print("Invalid selection, try again.")


def parse_write_value(s: str) -> bytes:
    """
    Accept:
      - plain text (default): e.g., Hello
      - hex: prefix with hex: or 0x, or space-separated hex pairs
        e.g., hex:01 02 0A 0D  or 01 02 0a 0d  or 0x01020a0d
      - escape sequences: prefix with str: to force string
    """
    s = s.strip()
    if s.lower().startswith("hex:"):
        s = s[4:].strip()
    if s.lower().startswith("0x"):
        s = s[2:].strip()
        s = "".join(s.split())
        return bytes.fromhex(s)
    # If it looks like space-separated hex pairs, parse as hex
    parts = s.split()
    if parts and all(all(c in "0123456789abcdefABCDEF" for c in p) and len(p) in (2, 4) for p in parts):
        try:
            return bytes.fromhex("".join(parts))
        except ValueError:
            pass
    # Force string if prefixed
    if s.lower().startswith("str:"):
        s = s[4:]
    return s.encode("utf-8")


async def list_and_pick_device():
    print(f"Scanning for BLE devices ({SCAN_SECONDS}s)…")
    devices = await BleakScanner.discover(timeout=SCAN_SECONDS)
    if not devices:
        print("No devices found. Try moving closer or increasing SCAN_SECONDS.")
        return None

    # De-dup by address
    unique: Dict[str, Tuple] = {}
    for d in devices:
        # In newer bleak versions, RSSI might not be directly accessible
        # We'll use a default value and focus on device discovery
        unique[d.address] = (d, d.name or "Unknown", None)

    items = list(unique.values())
    # Sort by address for consistent ordering since RSSI is not available
    items.sort(key=lambda x: x[0].address)

    print("\nFound devices:")
    for idx, (dev, name, _) in enumerate(items):
        print(f"[{idx}] {name} | addr={dev.address}")

    i = ask_index("Pick device", len(items))
    return items[i][0]  # BleakDevice


async def main():
    device = await list_and_pick_device()
    if not device:
        return

    print(f"\nConnecting to {device.name or 'Unknown'} ({device.address})…")
    async with BleakClient(device) as client:
        if not client.is_connected:
            print("Failed to connect.")
            return
        print("Connected.\nDiscovering services…")
        services = list(client.services)
        print(f"Discovered {len(services)} services.\n")

        # Map index -> characteristic for selection later
        writable: List[BleakGATTCharacteristic] = []

        idx_counter = 0
        for svc in services:
            print(f"Service {svc.uuid}")
            for ch in svc.characteristics:
                props = ",".join(sorted(ch.properties))
                # Try to read if 'read' in props
                value_preview = ""
                if "read" in ch.properties:
                    try:
                        v = await client.read_gatt_char(ch)
                        value_preview = printable_bytes(v)
                    except Exception as e:
                        value_preview = f"(read error: {e})"
                print(f"  [{idx_counter}] Char {ch.uuid} | props={props}")
                if value_preview:
                    print(f"      value: {value_preview}")

                if "write" in ch.properties or "write-without-response" in ch.properties:
                    writable.append(ch)
                idx_counter += 1
            print()

        if not writable:
            print("No writable characteristics found on this device.")
            return

        # Make a compact, numbered list of writable ones
        print("Writable characteristics:")
        for i, ch in enumerate(writable):
            props = ",".join(sorted(ch.properties))
            print(f"  ({i}) {ch.uuid} | props={props}")

        w_idx = ask_index("Pick characteristic to WRITE", len(writable))
        target: BleakGATTCharacteristic = writable[w_idx]

        user_val = input(
            "Enter value to write "
            "(plain text, or 'hex:01 02 0A', or '0x01020a'): "
        )
        payload = parse_write_value(user_val)

        # Pick write mode
        with_response = "write" in target.properties
        try:
            await client.write_gatt_char(target, payload, response=with_response)
            print(f"Write OK to {target.uuid} ({'with' if with_response else 'without'} response).")
        except Exception as e:
            print(f"Write failed: {e}")
            return

        # If readable, show new value
        if "read" in target.properties:
            try:
                new_v = await client.read_gatt_char(target)
                print(f"New value: {printable_bytes(new_v)}")
            except Exception as e:
                print(f"Read-after-write failed: {e}")

    print("Disconnected.")


if __name__ == "__main__":
    asyncio.run(main())