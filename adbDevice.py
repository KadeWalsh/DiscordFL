from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.sign_pythonrsa import PythonRSASigner
from adb_shell.auth.keygen import keygen
import os
import json
import numpy as np
import cv2
import time
from functools import wraps


def retry_on_error(max_attempts=20, delay=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        time.sleep(delay)
                    continue
            raise RuntimeError(f"""Failed after {
                max_attempts} attempts. Last error: {
                str(last_exception)}""")
        return wrapper
    return decorator


class ADBdevice:
    def __init__(self,
                 config_data: json):
        """Initialize ADBdevice with configuration from JSON file.

        Args:
            device_name (str):  Name of the device configuration to use
                                (default: "default_device")
            config_file (str):  Path to the configuration file
                                (default: "config.json")
        """
        self.config = config_data
        self._setup_adb_auth()
        self._connect_device()

    def _load_config(self, config_file: str, device_name: str) -> dict:
        """Load device configuration from JSON file.

        Args:
            config_file (str): Path to the configuration file
            device_name (str): Name of the device configuration to use

        Returns:
            Dict: Device configuration
        """
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)

            # Check if ADB section exists
            if 'adb' not in config or 'devices' not in config['adb']:
                raise ValueError(
                    "Invalid config file: missing 'adb.devices' section")

            # Find the specified device configuration
            for device in config['adb']['devices']:
                if device['name'] == device_name:
                    return device

            raise ValueError(
                f"Device '{device_name}' not found in configuration")
        except FileNotFoundError:
            raise FileNotFoundError(f"""Configuration file '{
                                    config_file}' not found""")
        except json.JSONDecodeError:
            raise ValueError(
                f"Invalid JSON in configuration file '{config_file}'")

    def _setup_adb_auth(self):
        """Setup ADB authentication using RSA keys."""
        adbkey_path = os.path.expanduser('~/.android/adbkey')
        if not os.path.exists(adbkey_path):
            keygen(adbkey_path)

        with open(adbkey_path) as f:
            priv = f.read()
        with open(adbkey_path + '.pub') as f:
            pub = f.read()

        self.signer = PythonRSASigner(pub, priv)

    @retry_on_error(max_attempts=3, delay=1)
    def _connect_device(self):
        """Establish connection to the Android device."""
        self.device = AdbDeviceTcp(
            self.config['host'],
            self.config['port'],
            default_transport_timeout_s=self.config.get('timeout', 9.0)
        )
        self.device.connect(
            rsa_keys=[self.signer],
            auth_timeout_s=self.config.get('auth_timeout', 0.1)
        )

    @retry_on_error(max_attempts=3, delay=1)
    def execute_shell_command(self, command: str) -> tuple[str, str]:
        """Execute an ADB shell command on the device.

        Args:
            command (str): The shell command to execute

        Returns:
            Tuple[str, str]: A tuple containing (stdout, stderr)
        """
        result = self.device.shell(command)
        return result.strip(), ""

    @retry_on_error(max_attempts=3, delay=1)
    def disconnect(self):
        """Safely disconnect from the device."""
        if hasattr(self, 'device'):
            self.device.close()

    def __del__(self):
        """Cleanup when the object is destroyed."""
        try:
            self.disconnect()
        except Exception as e:
            print(f"Error during cleanup: {e}")

    @retry_on_error(max_attempts=3, delay=1)
    def capture_screenshot(self, filename=None):
        """Capture a screenshot from the device.

        Args:
            filename (str, optional): If provided, save the screenshot to file

        Returns:
            numpy.ndarray: The screenshot as a numpy array
        """
        ss = self.device.exec_out('screencap -p', decode=False)
        image_np = np.frombuffer(ss, np.uint8)
        screenshot = cv2.imdecode(image_np, cv2.IMREAD_COLOR)

        if filename is not None:
            cv2.imwrite(filename, screenshot)

        return screenshot

    @retry_on_error(1, 1)
    def is_game_running(self, game_name='com.fun.lastwar.gp'):
        command = "ps -A"
        raw_results = self.execute_shell_command(command)
        result_list = list(raw_results)[0].split('\n')

        MIN_SIZE = 1000000
        for result in result_list[1:]:
            if game_name in result:
                RSS = result.split(None, 9)[4]
                if int(RSS) >= MIN_SIZE:
                    return True

        return False

    @retry_on_error()
    def start_game(self, name='com.fun.lastwar.gp'):
        command = f"monkey -p  {name} -c android.intent.category.LAUNCHER 1"
        self.execute_shell_command(command)

    def stop_game(self, name='com.fun.lastwar.gp'):
        command = f"am force-stop {name}"
        self.execute_shell_command(command)
