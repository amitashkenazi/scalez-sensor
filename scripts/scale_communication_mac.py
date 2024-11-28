import serial
import time
import binascii

def connect_to_scale(port='/dev/tty.PL2303G-USBtoUART1110', baudrate=1200):  # Changed to 1200
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1
        )
        
        if ser.is_open:
            print(f"Connected to {port}")
            return ser
            
    except serial.SerialException as e:
        print(f"Error: {e}")
        return None

def read_weight(ser):
    try:
        if ser.in_waiting:
            raw_data = ser.readline()
            print(f"Raw bytes: {binascii.hexlify(raw_data)}")
            return raw_data.decode('latin-1')
        return None
        
    except serial.SerialException as e:
        print(f"Error: {e}")
        return None

def main():
    ser = connect_to_scale()
    if not ser:
        return
    
    try:
        print("Reading weight... (Ctrl+C to stop)")
        while True:
            weight_data = read_weight(ser)
            if weight_data:
                print(f"Data: {weight_data}")
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        if ser and ser.is_open:
            ser.close()
            print("Connection closed")

if __name__ == "__main__":
    main()