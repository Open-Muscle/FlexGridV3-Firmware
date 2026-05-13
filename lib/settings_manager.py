# lib/settings_manager.py

import json
import uos


class SettingsManager:
    DEFAULTS = {
        "wifi_ssid": "OpenMuscle",
        "wifi_password": "3141592653",
        "udp_target_ip": "192.168.1.49",
        "udp_port": 3141,
        "scan_interval_ms": 100,
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
