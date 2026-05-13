# flexgrid.py
# OpenMuscle FlexGrid V3 — main application.

import asyncio
import gc
import uos
import logger

from settings_manager import SettingsManager
from sensor_matrix    import SensorMatrix
from display_manager  import DisplayManager
from menu_manager     import MenuManager
from network_manager  import NetworkManager
from power_manager    import PowerManager


async def sensor_loop(sensor_matrix, network, interval_ms):
    """Scan the matrix and broadcast over UDP. No display work here — too slow."""
    while True:
        matrix = sensor_matrix.scan_matrix()
        await network.send_udp(matrix)
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


async def status_loop(power, network):
    """Periodic battery + Wi-Fi heartbeat to the REPL."""
    while True:
        v = power.battery_voltage()
        p = power.battery_percent()
        wifi = "WiFi:ok" if network.is_connected() else "WiFi:--"
        logger.info("BAT {:.2f}V ({}%)  {}".format(v, p, wifi))
        await asyncio.sleep(5)


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
    asyncio.create_task(status_loop(power, network))
    asyncio.create_task(gc_loop())

    while True:
        await asyncio.sleep(1)
