import time
import json
import hashlib
import base64

def mock_aes_encrypt(data_dict, key="hydro-kinematic-secret-key"):
    """Mock AES-256 encryption."""
    json_data = json.dumps(data_dict)
    # Simple XOR-based mock encryption for demonstration
    encrypted = ''.join(chr(ord(c) ^ ord(k)) for c, k in zip(json_data, key * (len(json_data) // len(key) + 1)))
    return base64.b64encode(encrypted.encode('utf-8')).decode('utf-8')

def mock_aes_decrypt(encrypted_str, key="hydro-kinematic-secret-key"):
    """Mock AES-256 decryption."""
    encrypted = base64.b64decode(encrypted_str.encode('utf-8')).decode('utf-8')
    decrypted = ''.join(chr(ord(c) ^ ord(k)) for c, k in zip(encrypted, key * (len(encrypted) // len(key) + 1)))
    return json.loads(decrypted)

def generate_digital_signature(payload_str, private_key="node-private-key"):
    """Mock ECDSA digital signature generation using SHA256 HMAC."""
    return hashlib.sha256(f"{payload_str}:{private_key}".encode()).hexdigest()

class VDTNNode:
    def __init__(self, node_id, is_fleeing=False):
        self.node_id = node_id
        self.is_fleeing = is_fleeing
        self.message_buffer = []
        self.cellular_connected = True
        
    def enter_dead_zone(self):
        self.cellular_connected = False
        print(f"[{self.node_id}] Entered cellular dead zone. Switching to VDTN Mesh.")
        
    def generate_telemetry(self, location, depth, velocity):
        # Create raw telemetry data
        hazard_coef = depth * velocity
        raw_telemetry = {
            "source": self.node_id,
            "timestamp": time.time(),
            "location": location,
            "flow_depth": depth,
            "flow_velocity": velocity,
            "hazard_coefficient": hazard_coef
        }
        
        print(f"[{self.node_id}] Generating telemetry: hazard {hazard_coef:.2f} m^2/s at {location}")
        print(f"[{self.node_id}] Encrypting (AES-256) and signing payload...")
        
        # Encrypt payload
        encrypted_payload = mock_aes_encrypt(raw_telemetry)
        
        # Generate signature
        signature = generate_digital_signature(encrypted_payload)
        
        # Package secure message
        secure_message = {
            "encrypted_payload": encrypted_payload,
            "signature": signature,
            "sender_id": self.node_id
        }
        self.message_buffer.append(secure_message)
        print(f"[{self.node_id}] Secure message buffered for VDTN forwarding.")
        
    def wifi_direct_handshake(self, other_node):
        print(f"\n[VDTN] Initiating Wi-Fi Direct handshake between {self.node_id} and {other_node.node_id}")
        # Store, carry, and forward
        if self.message_buffer:
            print(f"[{self.node_id}] Transferring {len(self.message_buffer)} secure messages to {other_node.node_id}")
            other_node.message_buffer.extend(self.message_buffer)
            self.message_buffer = []
            
        if other_node.message_buffer:
            print(f"[{other_node.node_id}] Transferring {len(other_node.message_buffer)} secure messages to {self.node_id}")
            self.message_buffer.extend(other_node.message_buffer)
            other_node.message_buffer = []

    def evaluate_route(self):
        # Examine buffer for critical hazards ahead
        for msg in self.message_buffer:
            # Verify signature
            expected_sig = generate_digital_signature(msg['encrypted_payload'])
            if msg['signature'] != expected_sig:
                print(f"[{self.node_id}] SECURITY ALERT: Invalid signature from {msg['sender_id']}! Dropping payload.")
                continue
            
            # Decrypt payload
            try:
                decrypted = mock_aes_decrypt(msg['encrypted_payload'])
                print(f"[{self.node_id}] Successfully verified and decrypted payload from {decrypted['source']}.")
                
                if decrypted['hazard_coefficient'] > 0.8:
                    print(f"[{self.node_id}] CRITICAL: Hazard coefficient {decrypted['hazard_coefficient']:.2f} > 0.8 m^2/s ahead at {decrypted['location']}.")
                    print(f"[{self.node_id}] Executing kinematic rerouting maneuver entirely offline!")
                    return True
            except Exception as e:
                print(f"[{self.node_id}] Decryption failed: {e}")
                
        return False

# Simulation
if __name__ == "__main__":
    # Simulate truck (FMCG transport) entering a dead zone
    truck = VDTNNode("Truck-FMCG-01", is_fleeing=False)
    truck.enter_dead_zone()
    print("-" * 50)
    
    # Simulate a fleeing vehicle coming from the flood zone
    fleeing_vehicle = VDTNNode("Fleeing-Vehicle-02", is_fleeing=True)
    # Fleeing vehicle experienced flash flood: y=1.2m, V=2.0m/s
    fleeing_vehicle.generate_telemetry("NH544-Chalakudy-Bridge", 1.2, 2.0)
    print("-" * 50)
    
    # They intercept each other
    truck.wifi_direct_handshake(fleeing_vehicle)
    print("-" * 50)
    
    # Truck's edge node instantaneously calculates hazard and reroutes
    truck.evaluate_route()
