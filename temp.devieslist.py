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
    print("\nReceived exit signal, cleaning up...")
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
    print("Use w/s to navigate, Enter to select, q to quit, r to refresh")
    print("-" * 50)
    
    if not devices:
        print("No devices found. Scanning...")
        return
    
    # Find the longest device name for proper alignment
    max_name_length = max(len(device['name']) for device in devices) if devices else 0
    max_name_length = max(max_name_length, 8)  # Minimum width for "Device" header
    
    # Print header with proper alignment
    print(f"{'Device':<{max_name_length}} | {'UUID'} | {'Discovered'}")
    print("-" * (max_name_length + 2) + "+" + "-" * 37 + "+" + "-" * 12)
    
    for i, device in enumerate(devices):
        # Format discovery time
        if 'discovered' in device:
            time_ago = int(time.time() - device['discovered'])
            time_str = f"{time_ago}s ago"
        else:
            time_str = "unknown"
            
        # Align device name and format the line
        device_name = device['name'][:max_name_length]  # Truncate if too long
        if i == selected_index:
            print(f"  > {device_name:<{max_name_length}} | {device['address']} | {time_str}")  # Selected line
        else:
            print(f"    {device_name:<{max_name_length}} | {device['address']} | {time_str}")  # Other lines
    
    print("-" * 50)
    print(f"Selected: {devices[selected_index]['name'] if devices else 'None'}")
    print(f"Total devices: {len(devices)}")
    if devices:
        last_scan_time = min(device.get('discovered', time.time()) for device in devices)
        print(f"Last scan: {int(time.time() - last_scan_time)}s ago")
    else:
        print("No devices yet")

def get_key():
    """Get a single key press without waiting for Enter."""
    if os.name == 'nt':  # Windows
        import msvcrt
        key = msvcrt.getch()
        # Check for arrow keys (Windows sends 224 followed by direction)
        if key == b'\xe0':
            arrow = msvcrt.getch()
            if arrow == b'H': return 'up'
            elif arrow == b'P': return 'down'
            elif arrow == b'K': return 'left'
            elif arrow == b'M': return 'right'
        return key.decode('utf-8').lower()
    else:  # Unix/Linux/macOS
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
            
            # Check for arrow keys (ESC [ A/B/C/D)
            if ch == '\x1b':
                next_ch = sys.stdin.read(1)
                if next_ch == '[':
                    arrow = sys.stdin.read(1)
                    if arrow == 'A': return 'up'
                    elif arrow == 'B': return 'down'
                    elif arrow == 'C': return 'right'
                    elif arrow == 'D': return 'left'
            
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
        
        print("\nNavigation: w(up) s(down) Enter(select) r(refresh) q(quit)")
        
        try:
            # Get single key press
            key = get_key()
            
            if key == 'q':
                return None
            elif key == '\r' or key == '\n':  # Enter key
                if 0 <= selected_index < len(devices):
                    return devices[selected_index]
                else:
                    print("Device no longer available")
                    time.sleep(1)
            elif key == 'w' or key == 'up':
                selected_index = max(0, selected_index - 1)
            elif key == 's' or key == 'down':
                selected_index = min(len(devices) - 1, selected_index + 1)
            elif key == 'r':  # Manual refresh
                print("Refreshing device list...")
                time.sleep(1)  # Show message briefly
            elif key.isdigit():
                num = int(key)
                if 0 <= num < len(devices):
                    return devices[num]
                else:
                    print(f"Invalid number. Must be 0-{len(devices)-1}")
                    time.sleep(1)
                
        except KeyboardInterrupt:
            print("\nKeyboard interrupt, exiting...")
            return None
        except Exception as e:
            print(f"Input error: {e}")
            time.sleep(1)  # Brief pause on error

async def scan_and_select_device():
    """Scan for devices and let user select one."""
    print("Scanning for BLE devices...")
    print("Press Ctrl+C to stop")
    
    devices = []
    seen_addresses = set()
    last_scan_time = 0
    scan_interval = 10  # Scan every 10 seconds
    
    try:
        while True:
            current_time = time.time()
            
            # Only scan if enough time has passed
            if current_time - last_scan_time >= scan_interval:
                print(f"\nScanning for new devices... (last scan: {int(current_time - last_scan_time)}s ago)")
                
                # Scan for new devices
                current_devices = await BleakScanner.discover(timeout=5.0)
                
                # Add new devices to our list
                new_devices_found = 0
                for device in current_devices:
                    if device.address not in seen_addresses:
                        device_info = {
                            'name': device.name or 'Unknown',
                            'address': device.address,
                            'device': device,
                            'discovered': current_time
                        }
                        devices.append(device_info)
                        seen_addresses.add(device.address)
                        new_devices_found += 1
                
                if new_devices_found > 0:
                    print(f"Found {new_devices_found} new device(s)")
                
                last_scan_time = current_time
            
            # Show menu if we have devices
            if devices:
                return interactive_menu(devices)
            
            # Wait before next iteration
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        print("\nKeyboard interrupt during scan, exiting...")
    except Exception as e:
        print(f"Unexpected scan error: {e}")
    
    return None

async def connect_to_device(device_info):
    """Connect to the selected device."""
    device = device_info['device']
    print(f"\nConnecting to {device_info['name']} ({device.address})...")
    
    try:
        async with BleakClient(device, timeout=10.0) as client:
            if not client.is_connected:
                print("Failed to connect.")
                return False
            
            print("Connected successfully!")
            print("Discovering services...")
            
            services = list(client.services)
            print(f"Found {len(services)} services:")
            
            for svc in services:
                print(f"  Service: {svc.uuid}")
                for ch in svc.characteristics:
                    props = ",".join(sorted(ch.properties))
                    print(f"    Char: {ch.uuid} | props={props}")
            
            print("\nConnection established. Press Enter to disconnect...")
            try:
                input()
            except (KeyboardInterrupt, EOFError):
                print("\nDisconnecting...")
            
        return True
        
    except asyncio.CancelledError:
        print("\nConnection cancelled")
        return False
    except Exception as e:
        print(f"Connection error: {e}")
        return False

async def main():
    """Main function."""
    try:
        print("BLE Device Scanner and Connector")
        print("=" * 50)
        
        # Setup signal handlers
        setup_signal_handlers()
        
        # Scan and select device
        selected_device = await scan_and_select_device()
        
        if selected_device:
            # Connect to selected device
            await connect_to_device(selected_device)
        else:
            print("No device selected, exiting...")
            
    except KeyboardInterrupt:
        print("\nKeyboard interrupt in main, exiting...")
    except Exception as e:
        print(f"Unexpected error in main: {e}")
    finally:
        print("Cleaning up...")
        print("Goodbye!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nKeyboard interrupt, exiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
    finally:
        print("Application terminated.")