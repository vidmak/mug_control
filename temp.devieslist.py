import asyncio
import time
import sys
import os
import signal
import tty
import termios
from bleak import BleakScanner, BleakClient

def signal_handler(signum, frame):
    """Handle system signals for clean exit."""
    print("\n🔄 Received exit signal, cleaning up...")
    sys.exit(0)

def setup_signal_handlers():
    """Setup signal handlers for clean exit."""
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

def clear_screen():
    """Clear the console screen."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_menu(devices, selected_index):
    """Print the device selection menu with cursor."""
    clear_screen()
    print("BLE Device Scanner and Connector")
    print("=" * 50)
    print("Use w/s to navigate, Enter to select, q to quit")
    print("-" * 50)
    
    if not devices:
        print("No devices found. Scanning...")
        return
    
    for i, device in enumerate(devices):
        if i == selected_index:
            print(f"  ▶ {device['name']} - {device['address']}")  # Selected line
        else:
            print(f"    {device['name']} - {device['address']}")  # Other lines
    
    print("-" * 50)
    print(f"Selected: {devices[selected_index]['name'] if devices else 'None'}")
    print(f"Total devices: {len(devices)}")

def get_key():
    """Get a single key press without waiting for Enter."""
    if os.name == 'nt':  # Windows
        import msvcrt
        return msvcrt.getch().decode('utf-8').lower()
    else:  # Unix/Linux/macOS
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
            return ch.lower()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def interactive_menu(devices):
    """Interactive menu with immediate key response."""
    if not devices:
        return None
    
    selected_index = 0
    
    while True:
        print_menu(devices, selected_index)
        
        print("\nNavigation: w(up) s(down) Enter(select) q(quit)")
        
        try:
            # Get single key press
            key = get_key()
            
            if key == 'q':
                return None
            elif key == '\r' or key == '\n':  # Enter key
                return devices[selected_index]
            elif key == 'w':
                selected_index = max(0, selected_index - 1)
            elif key == 's':
                selected_index = min(len(devices) - 1, selected_index + 1)
            elif key.isdigit():
                num = int(key)
                if 0 <= num < len(devices):
                    return devices[num]
                # If it's a multi-digit number, we'd need to handle that differently
                # For now, just single digits work
                
        except KeyboardInterrupt:
            print("\n🔄 Keyboard interrupt, exiting...")
            return None
        except Exception as e:
            print(f"⚠️  Input error: {e}")
            time.sleep(1)  # Brief pause on error

async def scan_and_select_device():
    """Scan for devices and let user select one."""
    print("Scanning for BLE devices...")
    print("Press Ctrl+C to stop")
    
    devices = []
    seen_addresses = set()
    
    try:
        while True:
            try:
                # Scan for new devices
                current_devices = await BleakScanner.discover(timeout=3.0)
                
                # Add new devices to our list
                for device in current_devices:
                    if device.address not in seen_addresses:
                        device_info = {
                            'name': device.name or 'Unknown',
                            'address': device.address,
                            'device': device
                        }
                        devices.append(device_info)
                        seen_addresses.add(device.address)
                
                # Show menu if we have devices
                if devices:
                    return interactive_menu(devices)
                
                # Wait before next scan
                await asyncio.sleep(1)
                
            except asyncio.CancelledError:
                print("\n🔄 Scan cancelled, exiting...")
                break
            except Exception as e:
                print(f"⚠️  Scan error: {e}")
                await asyncio.sleep(1)
                
    except KeyboardInterrupt:
        print("\n🔄 Keyboard interrupt during scan, exiting...")
    except Exception as e:
        print(f"⚠️  Unexpected scan error: {e}")
    
    return None

async def connect_to_device(device_info):
    """Connect to the selected device."""
    device = device_info['device']
    print(f"\n🔗 Connecting to {device_info['name']} ({device.address})...")
    
    try:
        async with BleakClient(device, timeout=10.0) as client:
            if not client.is_connected:
                print("❌ Failed to connect.")
                return False
            
            print("✅ Connected successfully!")
            print("🔍 Discovering services...")
            
            services = list(client.services)
            print(f"📋 Found {len(services)} services:")
            
            for svc in services:
                print(f"  Service: {svc.uuid}")
                for ch in svc.characteristics:
                    props = ",".join(sorted(ch.properties))
                    print(f"    Char: {ch.uuid} | props={props}")
            
            print("\n🔗 Connection established. Press Enter to disconnect...")
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                print("\n🔄 Disconnecting...")
            
        return True
        
    except asyncio.CancelledError:
        print("\n🔄 Connection cancelled")
        return False
    except Exception as e:
        print(f"❌ Connection error: {e}")
        return False

async def main():
    """Main function."""
    try:
        print("🚀 BLE Device Scanner and Connector")
        print("=" * 50)
        
        # Setup signal handlers
        setup_signal_handlers()
        
        # Scan and select device
        selected_device = await scan_and_select_device()
        
        if selected_device:
            # Connect to selected device
            await connect_to_device(selected_device)
        else:
            print("👋 No device selected, exiting...")
            
    except KeyboardInterrupt:
        print("\n🔄 Keyboard interrupt in main, exiting...")
    except Exception as e:
        print(f"❌ Unexpected error in main: {e}")
    finally:
        print("🧹 Cleaning up...")
        print("👋 Goodbye!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🔄 Keyboard interrupt, exiting...")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
    finally:
        print("👋 Application terminated.")