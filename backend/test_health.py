#!/usr/bin/env python
"""
Quick test to check if backend health endpoint responds.
"""
import sys
import socket
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config import Config

def test_health():
    """Test health endpoint with timeout."""
    try:
        config = Config()
        backend_config = config.get_backend_config()
        port = backend_config['port']
        host = '127.0.0.1'
        
        print(f"Testing backend health on {host}:{port}...")
        
        # Test port connectivity first
        print("1. Checking if port is open...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result != 0:
            print(f"   ❌ Port {port} is NOT open")
            print(f"   Backend is not running!")
            return False
        else:
            print(f"   ✓ Port {port} is open")
        
        # Test health endpoint with short timeout
        print("2. Testing /health endpoint...")
        try:
            response = requests.get(f"http://{host}:{port}/health", timeout=2)
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
            if response.status_code == 200:
                print("   ✓ /health endpoint works!")
                return True
            else:
                print(f"   ❌ /health returned status {response.status_code}")
                return False
        except requests.exceptions.Timeout:
            print("   ❌ /health endpoint timed out (backend is hung)")
            print("   Backend is running but not responding to requests")
            print("   Recommendation: Restart the backend")
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"   ❌ Connection error: {e}")
            return False
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_health()
    sys.exit(0 if success else 1)













