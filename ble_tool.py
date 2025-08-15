# ble_tool.py
# Simple BLE CLI for macOS using bleak
# - Automatically scan for specific mug device
# - Connect and display status
# - Write to characteristics when needed

import asyncio
import time
from typing import Optional
from bleak import BleakScanner, BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

# Configuration
TARGET_DEVICE_ADDRESS = "C0AFF08D-F255-248A-1317-30DE4080E377"
SCAN_INTERVAL = 5  # seconds between scans
CONNECTION_TIMEOUT = 10  # seconds to wait for connection

# Characteristic UUIDs
TARGET_TEMP_CHAR = "fc540003-236c-4c94-8fa9-944a3e5353fa"
DRINK_TEMP_CHAR = "fc540002-236c-4c94-8fa9-944a3e5353fa"

def printable_bytes(b: bytes, max_len: int = 64) -> str:
    """Show both hex and (best-effort) UTF-8 preview."""
    hex_part = b[:max_len].hex(" ")
    try:
        text = b.decode("utf-8")
        text_part = text if len(text) <= max_len else text[:max_len] + "…"
    except UnicodeDecodeError:
        text_part = "⟂"
    return f"hex[{hex_part}] | utf8[{text_part}]"


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


async def find_target_device() -> Optional[object]:
    """Continuously scan for the target mug device."""
    print(f"🔍 Looking for mug device: {TARGET_DEVICE_ADDRESS}")
    
    while True:
        try:
            print(f"📡 Scanning... (every {SCAN_INTERVAL}s)")
            devices = await BleakScanner.discover(timeout=SCAN_INTERVAL)
            
            for device in devices:
                if device.address == TARGET_DEVICE_ADDRESS:
                    print(f"✅ Found target device: {device.name or 'Unknown'} ({device.address})")
                    return device
            
            print("❌ Target device not found, retrying...")
            
        except Exception as e:
            print(f"⚠️  Scan error: {e}")
        
        await asyncio.sleep(1)  # Brief pause before next scan


async def connect_and_monitor(device):
    """Connect to device and monitor status."""
    print(f"🔗 Attempting to connect to {device.name or 'Unknown'}...")
    
    try:
        async with BleakClient(device, timeout=CONNECTION_TIMEOUT) as client:
            if not client.is_connected:
                print("❌ Failed to connect")
                return False
            
            print("✅ Connected successfully!")
            print("🔍 Discovering services...")
            
            services = list(client.services)
            print(f"📋 Found {len(services)} services")
            
            # Find both temperature characteristics
            target_char = None
            drink_char = None
            
            for svc in services:
                for ch in svc.characteristics:
                    if ch.uuid == TARGET_TEMP_CHAR:
                        target_char = ch
                        print(f"🎯 Found target temperature characteristic: {ch.uuid}")
                    elif ch.uuid == DRINK_TEMP_CHAR:
                        drink_char = ch
                        print(f"🌡️  Found drink temperature characteristic: {ch.uuid}")
                if target_char and drink_char:
                    break
            
            if not target_char:
                print("⚠️  Target temperature characteristic not found")
                return True
                
            if not drink_char:
                print("⚠️  Drink temperature characteristic not found")
                return True
            
            # Monitor connection status
            print("📊 Monitoring temperatures...")
            print("💡 Use Ctrl+C to exit")
            print("-" * 50)
            
            while client.is_connected:
                try:
                    current_time = time.strftime("%H:%M:%S")
                    
                    # Read target temperature
                    if "read" in target_char.properties:
                        try:
                            target_value = await client.read_gatt_char(target_char)
                            target_temp = int.from_bytes(target_value, byteorder='little') / 100.0
                        except Exception as e:
                            target_temp = "Error"
                    else:
                        target_temp = "Not readable"
                    
                    # Read current drink temperature
                    if "read" in drink_char.properties:
                        try:
                            drink_value = await client.read_gatt_char(drink_char)
                            drink_temp = int.from_bytes(drink_value, byteorder='little') / 100.0
                        except Exception as e:
                            drink_temp = "Error"
                    else:
                        drink_temp = "Not readable"
                    
                    # Display both temperatures
                    print(f"[{current_time}] 🎯 Target: {target_temp}°C | 🌡️ Drink: {drink_temp}°C")
                    
                    # Automatic temperature control logic
                    if isinstance(drink_temp, (int, float)) and isinstance(target_temp, (int, float)):
                        if drink_temp < 40.0:
                            # Drink is too cold, set target to 50°C (minimum heating)
                            if target_temp != 50.0:
                                try:
                                    # The mug expects big-endian, so to get 50°C we need 0x8813
                                    # 0x8813 in big-endian = 34867, but the mug scales it to 50°C
                                    new_target_bytes = bytes([0x88, 0x13])  # 0x8813 for 50°C
                                    print(f"   🔄 Using big-endian encoding (0x8813) for 50°C")
                                    
                                    # Check if characteristic supports write
                                    if "write" in target_char.properties:
                                        # Use write with response since write-without-response is not supported
                                        await client.write_gatt_char(target_char, new_target_bytes, response=True)
                                        print(f"🔥 Drink too cold ({drink_temp:.1f}°C), setting target to 50°C")
                                        print(f"   Wrote bytes: {new_target_bytes.hex(' ').upper()} to {target_char.uuid}")
                                    else:
                                        print(f"⚠️  Target characteristic doesn't support write operations")
                                        
                                except Exception as e:
                                    print(f"⚠️  Failed to set target temperature: {e}")
                                    print(f"   Characteristic properties: {target_char.properties}")
                        elif drink_temp > 40.0:
                            # Drink is warm enough, turn off heating
                            if target_temp != 0.0:
                                try:
                                    # Set target to 0°C to turn off heating
                                    off_bytes = bytes([0x00, 0x00])
                                    await client.write_gatt_char(target_char, off_bytes, response=True)
                                    print(f"❄️  Drink warm enough ({drink_temp:.1f}°C), turning off heating")
                                    print(f"   Wrote bytes: {off_bytes.hex(' ').upper()} to {target_char.uuid}")
                                except Exception as e:
                                    print(f"⚠️  Failed to turn off heating: {e}")
                                    print(f"   Characteristic properties: {target_char.properties}")
                    
                    # Wait before next check
                    await asyncio.sleep(3)
                    
                except asyncio.CancelledError:
                    break
                    
        return True
        
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False


async def set_target_temperature(client, target_char, temperature_celsius):
    """Manually set the target temperature."""
    try:
        # Convert temperature to the device's scale (×100)
        temp_value = int(temperature_celsius * 100)
        
        # Convert to little-endian bytes
        temp_bytes = temp_value.to_bytes(2, byteorder='little')
        
        # Write to characteristic without response
        await client.write_gatt_char(target_char, temp_bytes, response=False)
        
        print(f"✅ Target temperature set to {temperature_celsius}°C ({temp_bytes.hex(' ').upper()})")
        return True
        
    except Exception as e:
        print(f"❌ Failed to set temperature: {e}")
        return False


async def test_write_operations(client, target_char):
    """Test different write operations to debug the issue."""
    print("\n🧪 Testing write operations...")
    
    test_values = [
        (50.0, "50°C (minimum heating)"),
        (0.0, "0°C (off)"),
        (55.0, "55°C (test)"),
        (60.0, "60°C (test)")
    ]
    
    for temp, description in test_values:
        try:
            temp_value = int(temp * 100)
            temp_bytes = temp_value.to_bytes(2, byteorder='little')
            
            print(f"  Testing {description}: {temp_bytes.hex(' ').upper()}")
            
            # Try write with response
            if "write" in target_char.properties:
                await client.write_gatt_char(target_char, temp_bytes, response=True)
                print(f"    ✅ Write with response: OK")
            else:
                print(f"    ❌ Write with response: Not supported")
                
            # Wait a moment and read back
            await asyncio.sleep(1)
            try:
                read_value = await client.read_gatt_char(target_char)
                read_temp = int.from_bytes(read_value, byteorder='little') / 100.0
                print(f"    📖 Read back: {read_temp}°C ({read_value.hex(' ').upper()})")
            except Exception as e:
                print(f"    📖 Read back failed: {e}")
                
        except Exception as e:
            print(f"    ❌ Test failed: {e}")
        
        print()
    
    print("🧪 Write testing complete")


async def find_heating_control_characteristics(client, services):
    """Look for characteristics that might actually control the heating."""
    print("\n🔍 Searching for heating control characteristics...")
    
    # Look for characteristics with names or UUIDs that suggest heating control
    heating_keywords = ['heat', 'power', 'control', 'switch', 'enable', 'active']
    
    for svc in services:
        for ch in svc.characteristics:
            # Check if characteristic has a name that suggests heating control
            char_name = getattr(ch, 'name', '').lower()
            char_uuid = ch.uuid.lower()
            
            # Check if it's writable and might control heating
            if ("write" in ch.properties or "write-without-response" in ch.properties):
                is_heating_control = False
                
                # Check name for heating-related keywords
                for keyword in heating_keywords:
                    if keyword in char_name or keyword in char_uuid:
                        is_heating_control = True
                        break
                
                # Check if it's a boolean/switch characteristic (1 byte)
                if len(ch.uuid) > 8:  # Custom UUID
                    is_heating_control = True
                
                if is_heating_control:
                    print(f"   🔥 Potential heating control: {ch.uuid}")
                    print(f"      Properties: {ch.properties}")
                    if hasattr(ch, 'name') and ch.name:
                        print(f"      Name: {ch.name}")
                    
                    # Try to read current value
                    try:
                        if "read" in ch.properties:
                            value = await client.read_gatt_char(ch)
                            print(f"      Current value: {value.hex(' ').upper()}")
                    except Exception as e:
                        print(f"      Read failed: {e}")
                    
                    print()


async def main():
    """Main function to find and connect to the target device."""
    print("🚀 Mug Control BLE Tool")
    print("=" * 40)
    
    try:
        # Find the target device
        device = await find_target_device()
        if not device:
            print("❌ Could not find target device")
            return
        
        # Connect and monitor
        success = await connect_and_monitor(device)
        if not success:
            print("❌ Failed to establish connection")
            
    except KeyboardInterrupt:
        print("\n👋 Exiting...")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    asyncio.run(main())