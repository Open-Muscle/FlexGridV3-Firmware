# lib/network_manager.py
# Wi-Fi + UDP broadcast for sensor matrix telemetry.
#
# v0.1.4: socket is created in __init__ (not deferred to connect()), so that
# Wi-Fi joining slower than the connect() timeout no longer leaves us
# permanently silent. sendto() failures while Wi-Fi is down are still
# handled gracefully in send_udp().

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

        # Create the UDP socket up front — doesn't require Wi-Fi to exist.
        # sendto() will fail until the interface is up; we guard for that
        # in send_udp() below.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

    async def connect(self):
        if not self.ssid:
            logger.warn("No Wi-Fi SSID configured; skipping connection")
            return

        if not self.sta.active():
            self.sta.active(True)

        if not self.sta.isconnected():
            logger.info("Connecting to Wi-Fi SSID='{}'".format(self.ssid))
            self.sta.connect(self.ssid, self.password)
            for _ in range(20):
                if self.sta.isconnected():
                    break
                await asyncio.sleep(1)
            if not self.sta.isconnected():
                # Not fatal — the Wi-Fi stack will keep retrying in the
                # background and send_udp() will start working once it's up.
                logger.warn("Wi-Fi did not join within 20s; will keep trying")
                return

        logger.info("Wi-Fi connected, IP: " + self.sta.ifconfig()[0])

    async def send_udp(self, matrix):
        # Early-out if Wi-Fi isn't currently up — avoids ujson.dumps allocation
        # at 50 Hz when there's no link.
        if not self.sta.isconnected():
            return
        try:
            self.sock.sendto(ujson.dumps(matrix), (self.udp_ip, self.udp_port))
        except Exception as e:
            logger.error("UDP send error: " + str(e))

    def is_connected(self):
        return self.sta.isconnected()
