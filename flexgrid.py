# flexgrid.py
# OpenMuscle FlexGrid V3 — main application.

import asyncio
import gc
import time
import uos
import logger

from settings_manager import SettingsManager
from sensor_matrix    import SensorMatrix
from display_manager  import DisplayManager
from menu_manager     import MenuManager
from network_manager  import NetworkManager
from power_manager    import PowerManager


# Shared device-status dict, refreshed periodically by status_loop and
# attached as the `meta` field on every outgoing sensor packet. Keeping it
# at module scope means the 50 Hz sensor_loop just reads the dict (no ADC
# read, no lock) while the slow status_loop is the only writer.
device_status = {
    "vbat":     None,
    "pct":      None,
    "uptime_s": 0,
    "free_mem": 0,
    "rssi":     None,
    "imu":      None,   # placeholder; populated when ICM-42688-P is soldered
}


async def sensor_loop(sensor_matrix, network, interval_ms):
    """Scan the matrix and broadcast over UDP. No display work here -- too slow.

    Attaches `device_status` as `meta` to ~1 packet per second only. The
    other ~49 packets at 50 Hz are lean -- if we put meta on every packet
    the larger payloads exhaust lwip's pbuf pool and we start dropping
    sends with [Errno 12] ENOMEM. 1 Hz is plenty for a battery readout
    in the UI; the PC merges meta keys non-destructively so stale fields
    persist between updates.
    """
    # Target ~1 Hz meta updates regardless of scan rate.
    meta_every = max(1, 1000 // max(1, interval_ms))
    n = 0
    while True:
        matrix = sensor_matrix.scan_matrix()
        n += 1
        meta = device_status if (n % meta_every == 0) else None
        await network.send_sensor(matrix, meta=meta)
        await asyncio.sleep_ms(interval_ms)


async def display_loop(display, sensor_matrix, menu, interval_ms=66):
    """Render at ~15 Hz independent of scan rate. I2C @ 400 kHz takes ~22 ms
    per full frame; 66 ms gives the bus plenty of slack and keeps CPU free."""
    while True:
        # If you wire a real OLED in, this draws the heatmap from the latest
        # scan. Without a display, draw_sensor_matrix is a no-op.
        display.draw_sensor_matrix(sensor_matrix.matrix)
        await asyncio.sleep_ms(interval_ms)


async def menu_loop(menu):
    """Poll buttons frequently for responsive UI."""
    while True:
        menu.check_buttons()
        await asyncio.sleep_ms(50)


async def status_loop(power, network, interval_s=5):
    """Refresh the shared `device_status` dict and emit a REPL heartbeat.

    Updates run at `interval_s` (default 5s) -- battery_voltage() is the
    only relatively expensive call here (64-sample ADC average over ~1ms)
    so doing it once every 5s costs nothing meaningful. The dict is read
    by sensor_loop on every UDP send to attach status as packet metadata.
    """
    while True:
        v = power.battery_voltage()
        p = power.battery_percent()
        uptime_s = time.ticks_ms() // 1000
        free_mem = gc.mem_free()
        rssi = network.rssi()
        # Mutate in place so sensor_loop's reference stays valid.
        device_status["vbat"]     = round(v, 3)
        device_status["pct"]      = p
        device_status["uptime_s"] = uptime_s
        device_status["free_mem"] = free_mem
        device_status["rssi"]     = rssi
        # imu stays None until the IMU sensor is wired in
        wifi = "WiFi:ok" if network.is_connected() else "WiFi:--"
        logger.info("BAT {:.2f}V ({}%) up={}s rssi={} mem={}  {}".format(
            v, p, uptime_s, rssi, free_mem, wifi))
        await asyncio.sleep(interval_s)


async def gc_loop(interval_s=2):
    """Manual GC pacing — ESP32 MicroPython tends to let heap fragment under
    steady allocation pressure. Periodic explicit collect keeps things flat."""
    while True:
        gc.collect()
        await asyncio.sleep(interval_s)


async def main():
    logger.info("FlexGrid V3 startup")

    try:
        uos.stat('config')
    except OSError:
        logger.warn("No config folder — creating")
        uos.mkdir('config')

    settings = SettingsManager.load()
    logger.info("Settings: {}".format(settings))

    power         = PowerManager()
    display       = DisplayManager()
    sensor_matrix = SensorMatrix()
    network       = NetworkManager(settings)
    menu          = MenuManager(display, network, power)

    display.text_screen([
        "OpenMuscle",
        "FlexGrid V3",
        "BAT {:.2f}V".format(power.battery_voltage()),
        "Booting...",
    ])

    try:
        await network.connect()
    except Exception as e:
        logger.error("Network: {}".format(e))

    logger.info("Spawning async tasks")
    asyncio.create_task(sensor_loop(sensor_matrix, network,
                                    settings.get("scan_interval_ms", 20)))
    asyncio.create_task(display_loop(display, sensor_matrix, menu))
    asyncio.create_task(menu_loop(menu))
    asyncio.create_task(status_loop(power, network,
                                    settings.get("status_interval_s", 5)))
    asyncio.create_task(gc_loop())

    while True:
        await asyncio.sleep(1)
