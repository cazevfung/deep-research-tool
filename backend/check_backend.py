#!/usr/bin/env python
"""
Quick script to check if the backend server is running.
"""
import sys
import socket
import requests
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config import Config


def check_backend():
    """Check if backend is running."""
    try:
        config = Config()
        backend_config = config.get_backend_config()
        port = backend_config['port']
        host = backend_config['host']
        
        # Check if port is open
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        
        if result != 0:
            print(f"❌ Backend is NOT running on port {port}")
            print(f"\nTo start the backend, run:")
            print(f"  python backend/run_server.py")
            return False
        
        # Try to connect to health endpoint
        try:
            url = f"http://127.0.0.1:{port}/health"
            response = requests.get(url, timeout=3)
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Backend is running on port {port}")
                print(f"   Status: {data.get('status', 'unknown')}")
                print(f"   Service: {data.get('service', 'unknown')}")
                return True
            else:
                print(f"⚠️  Backend is running but health check returned status {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Backend port is open but health check failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Error checking backend: {e}")
        return False


if __name__ == "__main__":
    check_backend()













