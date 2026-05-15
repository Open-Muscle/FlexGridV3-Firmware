# lib/network_manager.py
# Wi-Fi + UDP broadcast for sensor matrix telemetry.
#
# v0.1.4: socket is created in __init__ (not deferred to connect()), so that
#         Wi-Fi joining slower than the connect() timeout no longer leaves
#         us permanently silent. sendto() failures while Wi-Fi is down are
#         still handled gracefully in send_sensor() below.
# v0.2.0: emit OpenMuscle v1.0 protocol envelopes (`{v, type, id, ts, data,
#         meta}`) instead of bare matrix arrays. Adds a `meta` payload on
#         every sensor packet (vbat, pct, uptime_s, free_mem, rssi, imu)
#         so the PC can chart battery + heap over time and post-mortem the
#         last known state when a device drops off the air.

import network
import socket
import asyncio
import ujson
import time
import logger


PROTOCOL_VERSION = "1.0"


class NetworkManager:
    def __init__(self, settings):
        self.device_id = settings.get("device_id", "flexgrid-v3-01")
        self.device_type = settings.get("device_type", "flexgrid")
        self.ssid = settings.get("wifi_ssid", "").strip()
        self.password = settings.get("wifi_password", "").strip()
        self.udp_ip = settings.get("udp_target_ip", "255.255.255.255")
        self.udp_port = settings.get("udp_port", 3141)
        self.sta = network.WLAN(network.STA_IF)

        # Create the UDP socket up front -- doesn't require Wi-Fi to exist.
        # sendto() will fail until the interface is up; we guard for that
        # in send_sensor() below.
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
                # Not fatal -- the Wi-Fi stack will keep retrying in the
                # background and send_sensor() will start working once it's up.
                logger.warn("Wi-Fi did not join within 20s; will keep trying")
                return

        logger.info("Wi-Fi connected, IP: " + self.sta.ifconfig()[0])

    def rssi(self):
        """Current STA RSSI in dBm, or None if unknown."""
        try:
            return self.sta.status('rssi')
        except Exception:
            return None

    def _build_packet(self, data, meta=None):
        pkt = {
            "v": PROTOCOL_VERSION,
            "type": self.device_type,
            "id": self.device_id,
            "ts": time.ticks_ms(),
            "data": data,
        }
        if meta:
            pkt["meta"] = meta
        return pkt

    async def send_sensor(self, matrix, meta=None):
        """Send a sensor frame as a v1.0-wrapped UDP packet.

        Args:
            matrix: the [cols][rows] sensor matrix (passed through as-is).
            meta: optional dict (typically the device's cached status
                  -- vbat/pct/uptime/free_mem/rssi/imu). Attached to the
                  packet's `meta` field so the PC can read it without an
                  extra status packet round-trip.
        """
        if not self.sta.isconnected():
            return
        pkt = self._build_packet({"matrix": matrix}, meta=meta)
        try:
            self.sock.sendto(ujson.dumps(pkt), (self.udp_ip, self.udp_port))
        except Exception as e:
            logger.error("UDP send error: " + str(e))

    async def send_status(self, status):
        """Send a status-only packet (no matrix). Useful for keeping the
        device 'alive' on the PC's last_seen tracker even when sensor
        scanning is paused (e.g. while in a calibration menu).
        """
        if not self.sta.isconnected():
            return
        pkt = self._build_packet({}, meta=status)
        try:
            self.sock.sendto(ujson.dumps(pkt), (self.udp_ip, self.udp_port))
        except Exception as e:
            logger.error("UDP send error: " + str(e))

    # Back-compat shim. Older flexgrid.py implementations called
    # `send_udp(matrix)` directly with a bare list. Keep it working so we
    # can roll out the upgrade incrementally if needed.
    async def send_udp(self, matrix):
        await self.send_sensor(matrix)

    def is_connected(self):
        return self.sta.isconnected()
