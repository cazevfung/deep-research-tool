#!/usr/bin/env python
"""
Kill hung backend processes on port 3001.
"""
import sys
import subprocess
import socket
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.config import Config

def kill_backend():
    """Kill processes using port 3001."""
    try:
        config = Config()
        backend_config = config.get_backend_config()
        port = backend_config['port']
        
        print(f"Finding processes using port {port}...")
        
        # Use netstat to find processes using the port (Windows)
        try:
            result = subprocess.run(
                ['netstat', '-ano'],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Find lines with the port
            lines = result.stdout.split('\n')
            pids = []
            for line in lines:
                if f':{port}' in line and 'LISTENING' in line:
                    parts = line.split()
                    if len(parts) > 0:
                        pid = parts[-1]
                        if pid.isdigit():
                            pids.append(pid)
            
            if not pids:
                print(f"   No processes found using port {port}")
                print("   Backend may not be running")
                return False
            
            print(f"   Found {len(pids)} process(es) using port {port}: {', '.join(pids)}")
            
            # Kill each process with retry logic
            for pid in pids:
                print(f"   Killing process {pid}...")
                killed = False
                
                # First, check if process exists
                try:
                    check_result = subprocess.run(
                        ['tasklist', '/FI', f'PID eq {pid}'],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if pid not in check_result.stdout:
                        print(f"   ⚠ Process {pid} no longer exists (already terminated)")
                        killed = True
                except:
                    pass
                
                # Try to kill the process (with retries)
                if not killed:
                    for attempt in range(3):
                        try:
                            result = subprocess.run(
                                ['taskkill', '/F', '/PID', pid],
                                capture_output=True,
                                text=True,
                                timeout=5,
                                check=False  # Don't raise on error
                            )
                            
                            if result.returncode == 0:
                                print(f"   ✓ Killed process {pid}")
                                killed = True
                                break
                            elif result.returncode == 128:
                                # Process doesn't exist or already terminated
                                print(f"   ⚠ Process {pid} doesn't exist (may already be terminated)")
                                killed = True
                                break
                            else:
                                if attempt < 2:
                                    print(f"   ⚠ Attempt {attempt + 1} failed, retrying...")
                                    time.sleep(1)
                                else:
                                    print(f"   ⚠ Failed to kill process {pid} after 3 attempts (exit code: {result.returncode})")
                                    print(f"      Process may already be terminated or require admin privileges")
                        except Exception as e:
                            if attempt < 2:
                                print(f"   ⚠ Attempt {attempt + 1} error: {e}, retrying...")
                                time.sleep(1)
                            else:
                                print(f"   ⚠ Error killing process {pid}: {e}")
                
                # Verify process is actually killed
                if killed:
                    time.sleep(0.5)
                    try:
                        verify_result = subprocess.run(
                            ['tasklist', '/FI', f'PID eq {pid}'],
                            capture_output=True,
                            text=True,
                            timeout=5
                        )
                        if pid in verify_result.stdout:
                            print(f"   ⚠ Warning: Process {pid} still appears to be running")
                        else:
                            print(f"   ✓ Verified: Process {pid} is terminated")
                    except:
                        pass
            
            # Final verification - check if port is still in use
            time.sleep(1)
            port_free = True
            try:
                verify_result = subprocess.run(
                    ['netstat', '-ano'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if verify_result.returncode == 0:
                    lines = verify_result.stdout.split('\n')
                    still_running = [line for line in lines if f':{port}' in line and 'LISTENING' in line]
                    if still_running:
                        print(f"   ⚠ Warning: Port {port} may still be in use")
                        port_free = False
                    else:
                        print(f"   ✓ All processes killed and port {port} is free")
            except:
                print(f"   ⚠ Could not verify port status, but processes were terminated")
            
            return port_free
            
        except subprocess.CalledProcessError as e:
            print(f"   ❌ Error running netstat: {e}")
            return False
        except FileNotFoundError:
            print("   ❌ netstat not found (this script requires Windows)")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Killing Backend Processes")
    print("=" * 60)
    success = kill_backend()
    if success:
        print("\n✓ Backend processes killed. You can now restart the backend:")
        print("  python backend/run_server.py")
    else:
        print("\n❌ Failed to kill backend processes")
        print("You may need to manually kill the process or restart your computer")
    sys.exit(0 if success else 1)






