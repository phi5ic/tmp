import json
import hashlib
import base64

def mock_aes_encrypt(data_dict, key="hydro-kinematic-secret-key"):
    """Mock AES-256 encryption."""
    json_data = json.dumps(data_dict)
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
