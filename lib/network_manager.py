# lib/network_manager.py
# Wi-Fi + UDP broadcast for sensor matrix telemetry.

import network
import socket
import asyncio
import ujson
import logger


class NetworkManager:
    def __init__(self, settings):
        self.ssid = settings.get("wifi_ssid", "").strip()
        self.password = settings.get("wifi_password", "").strip()
        self.udp_ip = settings.get("udp_target_ip", "255.255.255.255")
        self.udp_port = settings.get("udp_port", 3141)
        self.sta = network.WLAN(network.STA_IF)
        self.sock = None

    async def connect(self):
        if not self.ssid:
            logger.warn("No Wi-Fi SSID configured; skipping connection")
            return

        if not self.sta.active():
            self.sta.active(True)

        if not self.sta.isconnected():
            logger.info(f"Connecting to Wi-Fi SSID='{self.ssid}'")
            self.sta.connect(self.ssid, self.password)
            for _ in range(20):
                if self.sta.isconnected():
                    break
                await asyncio.sleep(1)
            if not self.sta.isconnected():
                raise RuntimeError("Wi-Fi connection failed")
        logger.info("Wi-Fi connected, IP: " + self.sta.ifconfig()[0])

        if not self.sock:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.setblocking(False)

    async def send_udp(self, matrix):
        if not self.sock:
            return
        try:
            self.sock.sendto(ujson.dumps(matrix), (self.udp_ip, self.udp_port))
        except Exception as e:
            logger.error("UDP send error: " + str(e))

    def is_connected(self):
        return self.sta.isconnected()
