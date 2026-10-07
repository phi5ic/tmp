import time
from vdtn_crypto import mock_aes_encrypt, mock_aes_decrypt, generate_digital_signature

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
        
        encrypted_payload = mock_aes_encrypt(raw_telemetry)
        signature = generate_digital_signature(encrypted_payload)
        
        secure_message = {
            "encrypted_payload": encrypted_payload,
            "signature": signature,
            "sender_id": self.node_id
        }
        self.message_buffer.append(secure_message)
        print(f"[{self.node_id}] Secure message buffered for VDTN forwarding.")
        
    def wifi_direct_handshake(self, other_node):
        print(f"\n[VDTN] Initiating Wi-Fi Direct handshake between {self.node_id} and {other_node.node_id}")
        if self.message_buffer:
            print(f"[{self.node_id}] Transferring {len(self.message_buffer)} secure messages to {other_node.node_id}")
            other_node.message_buffer.extend(self.message_buffer)
            self.message_buffer = []
            
        if other_node.message_buffer:
            print(f"[{other_node.node_id}] Transferring {len(other_node.message_buffer)} secure messages to {self.node_id}")
            self.message_buffer.extend(other_node.message_buffer)
            other_node.message_buffer = []

    def evaluate_route(self):
        for msg in self.message_buffer:
            expected_sig = generate_digital_signature(msg['encrypted_payload'])
            if msg['signature'] != expected_sig:
                print(f"[{self.node_id}] SECURITY ALERT: Invalid signature from {msg['sender_id']}! Dropping payload.")
                continue
            
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
