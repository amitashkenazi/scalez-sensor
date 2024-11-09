#!/usr/bin/env python3

import serial
import time
import argparse

def read_scale(port="/dev/ttyUSB0", baud_rate=1200, timeout=10):
    """Read data from scale and print raw output"""
    print(f"\nConnecting to scale on {port} at {baud_rate} baud...")
    
    try:
        # Open serial connection
        ser = serial.Serial(
            port=port,
            baudrate=baud_rate,
            timeout=1,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE
        )
        
        print("Connection successful!")
        print(f"Port settings: {ser.get_settings()}")
        
        # Clear any pending data
        ser.reset_input_buffer()
        
        print("\nReading data for", timeout, "seconds...")
        print("Press Ctrl+C to stop\n")
        
        start_time = time.time()
        while (time.time() - start_time) < timeout:
            try:
                # Check if data is available
                if ser.in_waiting > 0:
                    # Read data
                    raw_data = ser.readline()
                    
                    # Print raw data in different formats
                    print("\n=== New Data Received ===")
                    print("Raw (hex):", " ".join([f"{b:02x}" for b in raw_data]))
                    print("Raw (dec):", " ".join([f"{b:3d}" for b in raw_data]))
                    print("Raw (chr):", " ".join([chr(b) if 32 <= b <= 126 else '.' for b in raw_data]))
                    
                    # Try to decode as string
                    try:
                        decoded = raw_data.decode('ascii').strip()
                        print("Decoded (ascii):", decoded)
                    except UnicodeDecodeError:
                        print("Decoded (ascii): [decode error]")
                        
                    try:
                        decoded = raw_data.decode('utf-8').strip()
                        print("Decoded (utf-8):", decoded)
                    except UnicodeDecodeError:
                        print("Decoded (utf-8): [decode error]")
                    
                    print("Length:", len(raw_data), "bytes")
                    print("=" * 30)
                
                time.sleep(0.1)  # Short sleep to prevent CPU overuse
                
            except KeyboardInterrupt:
                print("\nStopped by user")
                break
                
    except serial.SerialException as e:
        print(f"Error opening port: {e}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("\nPort closed")

def main():
    parser = argparse.ArgumentParser(description='Read data from scale')
    parser.add_argument('--port', default='/dev/ttyUSB0', help='Serial port')
    parser.add_argument('--baud', type=int, default=1200, help='Baud rate')
    parser.add_argument('--timeout', type=int, default=10, help='Read timeout in seconds')
    
    args = parser.parse_args()
    
    print("\nScale Test Utility")
    print("=" * 20)
    print(f"Port: {args.port}")
    print(f"Baud Rate: {args.baud}")
    print(f"Timeout: {args.timeout} seconds")
    
    read_scale(args.port, args.baud, args.timeout)

if __name__ == "__main__":
    main()