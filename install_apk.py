from adbDevice import ADBdevice
APK_NAME = 'clipper.apk'

ADB_SETTINGS = {
    "host": "192.168.0.198",
    "port": 5625
}

ADB = ADBdevice(ADB_SETTINGS)

command = f"install {APK_NAME}"
ADB.execute_shell_command(command)
