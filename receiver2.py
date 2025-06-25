import wifi
import socketpool
import usb_hid
import time
import math
from adafruit_hid.mouse import Mouse

# WiFi credentials
SSID = "smit"
PASSWORD = "kadu1234"

print("Connecting to WiFi...")
wifi.radio.connect(SSID, PASSWORD)
print(f"Connected! IP Address: {wifi.radio.ipv4_address}")

# Create a socket pool
pool = socketpool.SocketPool(wifi.radio)
server = pool.socket(pool.AF_INET, pool.SOCK_DGRAM)  # UDP socket

# Bind to a port (must match sender)
PORT = 12345
server.bind(("0.0.0.0", PORT))

print(f"Listening for data on port {PORT}...")

# Setup USB HID Mouse
mouse = Mouse(usb_hid.devices)

# Flex threshold for clicks
FLEX_THRESHOLD = 20000

# Adaptive Kalman Filter for cursor smoothing
class AdaptiveKalmanFilter:
    def __init__(self, process_variance=0.99995, measurement_variance=0.00014):
        self.x = 0  # State estimate
        self.p = 1  # Estimate uncertainty
        self.q = process_variance  # Process noise
        self.r = measurement_variance  # Measurement noise
        self.last_measurement = 0  # Track last measurement

    def update(self, measurement):
        # Calculate movement difference
        delta = abs(measurement - self.last_measurement)
        self.last_measurement = measurement

        # Adapt process noise based on movement speed
        if delta > 5:
            self.q = min(self.q * 1.2, 1e-1)  # Increase for fast movements
        else:
            self.q = max(self.q * 0.8, 1e-4)  # Decrease for slow movements

        # Adapt measurement noise based on sudden jumps (noise handling)
        if delta > 10:
            self.r = min(self.r * 1.5, 1e-1)
        else:
            self.r = max(self.r * 0.9, 1e-2)

        self.p += self.q  # Predict next uncertainty
        k = self.p / (self.p + self.r)  # Kalman gain
        self.x += k * (measurement - self.x)  # Update estimate
        self.p *= (1 - k)  # Reduce uncertainty
        return self.x  # Return filtered value

# Initialize filters for X and Y movements
kf_x = AdaptiveKalmanFilter()
kf_y = AdaptiveKalmanFilter()

# Fixed movement speed
FIXED_SPEED = 10  # Adjust this value for desired cursor speed
DEADZONE = 1     # Ignore small movements

while True:
    try:
        # Receive and decode bytes data
        memory = bytearray(256)  # Buffer to store incoming data
        num_bytes, addr = server.recvfrom_into(memory)  # Read into buffer
        received_data = memory[:num_bytes].decode("utf-8").strip()  # Decode valid bytes
        print(f"Received from {addr}: {received_data}")

        # Ensure correct format (expecting 6 values)
        values = received_data.split(",")
        if len(values) != 6:
            print("⚠️ Error: Incorrect data format received.")
            continue

        # Convert received values to float
        try:
            move_x, move_y, flex1_val, flex2_val, flex3_val, smooth_z = map(float, values)
        except ValueError:
            print("⚠️ Error: Data conversion failed.")
            continue

        # Apply Adaptive Kalman Filter for cursor smoothing
        smoothed_x = kf_x.update(move_x)
        smoothed_y = kf_y.update(move_y)

        # Apply deadzone to ignore minor unwanted movements
        if abs(smoothed_x) < 5:
            smoothed_x = 0
        if abs(smoothed_y) < 5:
            smoothed_y = 0

        # Ensure constant speed
        magnitude = math.sqrt(smoothed_x ** 2 + smoothed_y ** 2)
        if magnitude > 0:
            normalized_x = (smoothed_x / magnitude) * FIXED_SPEED
            normalized_y = (smoothed_y / magnitude) * FIXED_SPEED
        else:
            normalized_x, normalized_y = 0, 0  # No movement

        # Handle Drag & Drop (All flex sensors bent)
        if flex1_val < 4750 and flex2_val < 12750 and flex3_val < 480:
            mouse.press(Mouse.LEFT_BUTTON)  # Hold left click
            print("🖱️ Object Selected (Mouse Click)")
        elif flex1_val > 4750 and flex2_val > 12750 and flex3_val > 480:
            mouse.release(Mouse.LEFT_BUTTON)
            print("🖱️ Object Dropped (Mouse Release)")
        elif flex1_val < 4750:
            mouse.click(Mouse.LEFT_BUTTON)
            print("🖱️ Left Click!")
        elif flex2_val < 12000:
            mouse.click(Mouse.RIGHT_BUTTON)
            print("🖱️ Right Click!")

        # Move the cursor only if there is a significant movement
        if normalized_x != 0 or normalized_y != 0:
            mouse.move(x=int(round(normalized_y))-2, y=-int(round(normalized_x)))  # Invert Y-axis
            print(f"🖱️ Moving Cursor: X={int(round(normalized_y))}, Y={-int(round(normalized_x))}")
            time.sleep(0.0001)

    except Exception as e:
        print(f"⚠️ Socket error: {e}")
