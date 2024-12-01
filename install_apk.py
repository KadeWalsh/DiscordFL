from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
import os

APK_NAME = 'clipper.apk'

ADB_SETTINGS = {
    "host": "192.168.0.198",  # Must be a string
    "port": 5625  # Must be an integer
}


def install_apk(apk_filename):
    """
    Install an APK on the connected Android device using ADB.

    Args:
        apk_filename (str): The name or path of the APK file to install
    """
    device = None
    
    try:
        # Load the default ADB keys
        adbkey = os.path.expanduser('~/.android/adbkey')
        with open(adbkey) as f:
            priv = f.read()
        signer = PythonRSASigner('', priv)

        print("Connecting to device...")
        # Create ADB device directly with host and port
        host = str(ADB_SETTINGS["host"])  # Ensure host is a string
        port = int(ADB_SETTINGS["port"])  # Ensure port is an integer
        print(f"Attempting to connect to {host}:{port}")
        
        device = AdbDeviceTcp(host=host, port=port)
        device.connect(rsa_keys=[signer], auth_timeout_s=10)

        # Get the absolute path of the APK
        apk_path = os.path.abspath(apk_filename)
        remote_path = '/data/local/tmp/app.apk'

        print(f"Pushing {apk_filename} to device...")
        # First, push the APK to the device
        with open(apk_path, 'rb') as f:
            data = f.read()
            device.push(data, remote_path)

        print("Installing APK...")
        # Install using shell command with explicit timeout
        cmd = 'pm install -r /data/local/tmp/app.apk'
        result = device.shell(cmd, read_timeout_s=60)

        print("Cleaning up...")
        # Clean up the temporary file
        device.shell('rm /data/local/tmp/app.apk')

        if "Success" in result:
            print(f"Successfully installed {apk_filename}")
        else:
            print(f"Installation failed: {result}")

    except FileNotFoundError as e:
        if 'adbkey' in str(e):
            print("ADB key not found. Please ensure you have ADB set up with authentication.")
        else:
            print(f"Error: {str(e)}")
    except Exception as e:
        print(f"Error installing APK: {str(e)}")
    finally:
        try:
            if device and device.available:
                device.close()
            print("Disconnected from device")
        except Exception:
            pass


install_apk(APK_NAME)
