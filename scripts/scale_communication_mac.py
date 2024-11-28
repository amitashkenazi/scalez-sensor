import serial
import time

def connect_to_scale(port='/dev/tty.PL2303G-USBtoUART110', baudrate=9600):
    """
    Establishes connection with the scale using specified serial port.
    Returns serial connection object if successful.
    """
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
            print(f"Successfully connected to {port}")
            return ser
        
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        return None

def read_weight(ser):
    """
    Reads weight data from the scale.
    Returns the raw data received from the scale.
    """
    try:
        if ser.in_waiting:  # if data is available
            raw_data = ser.readline()
            return raw_data.decode('ascii').strip()
        return None
    except serial.SerialException as e:
        print(f"Error reading from scale: {e}")
        return None

def main():
    # Connect to the scale
    ser = connect_to_scale()
    if not ser:
        return
    
    try:
        print("Reading weight data (Press Ctrl+C to stop)...")
        while True:
            weight_data = read_weight(ser)
            if weight_data:
                print(f"Received data: {weight_data}")
            time.sleep(0.1)  # Small delay to prevent excessive CPU usage
            
    except KeyboardInterrupt:
        print("\nStopping weight reading...")
    finally:
        if ser and ser.is_open:
            ser.close()
            print("Serial connection closed")

if __name__ == "__main__":
    main()