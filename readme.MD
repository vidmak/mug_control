pip install bleak
python ble_tool.py

characteristic to WRITE 

Target Temp "fc540003-236c-4c94-8fa9-944a3e5353fa"

The temperature is sent as a 2-byte (16-bit) unsigned integer in little-endian format
const temperature = 55.0
const temperatureScale = 100
const encodedValue = temperature * temperatureScale  // 55.0 * 100 = 5500

// This gets encoded as 2 bytes in little-endian format:
// 5500 = 0x157C in hex
// Little-endian: [0x7C, 0x15]

0xA00F    40.0°C   

0x8813 це 50.0°C 
0x7C15 це 55.0°C 
0x0000 це 0°C 


