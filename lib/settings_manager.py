# lib/settings_manager.py

import json
import uos


class SettingsManager:
    DEFAULTS = {
        # Identity -- written into every outgoing v1.0 packet's "id" field so
        # the PC can distinguish multiple FlexGrids on the same network.
        "device_id": "flexgrid-v3-01",
        "device_type": "flexgrid",
        "wifi_ssid": "OpenMuscle",
        "wifi_password": "3141592653",
        "udp_target_ip": "192.168.1.49",
        "udp_port": 3141,
        "scan_interval_ms": 20,
        "status_interval_s": 5,       # how often power/wifi/heap status refreshes
        "display_brightness": 255,
    }

    @staticmethod
    def load():
        try:
            with open('config/settings.json', 'r') as f:
                d = json.load(f)
            # Backfill any missing defaults (handy across firmware upgrades)
            for k, v in SettingsManager.DEFAULTS.items():
                d.setdefault(k, v)
            return d
        except Exception:
            return SettingsManager.DEFAULTS.copy()

    @staticmethod
    def save(settings):
        try:
            try:
                uos.stat('config')
            except OSError:
                uos.mkdir('config')
            with open('config/settings.json', 'w') as f:
                json.dump(settings, f)
            return True
        except Exception as e:
            print("[ERR] Could not save settings:", e)
            return False
