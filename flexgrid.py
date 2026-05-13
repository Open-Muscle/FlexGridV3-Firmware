# flexgrid.py
# OpenMuscle FlexGrid V3 — main application.

import asyncio
import uos
import logger

from settings_manager import SettingsManager
from sensor_matrix    import SensorMatrix
from display_manager  import DisplayManager
from menu_manager     import MenuManager
from network_manager  import NetworkManager
from power_manager    import PowerManager


async def sensor_loop(sensor_matrix, network, display, interval_ms):
    """Scan the matrix, broadcast over UDP, render to OLED."""
    while True:
        matrix = sensor_matrix.scan_matrix()
        logger.debug(f"Scanned col0: {matrix[0]}")
        await network.send_udp(matrix)
        display.draw_sensor_matrix(matrix)
        await asyncio.sleep_ms(interval_ms)


async def menu_loop(menu):
    """Poll buttons frequently for responsive UI."""
    while True:
        menu.check_buttons()
        await asyncio.sleep_ms(50)


async def status_loop(power, network, display):
    """Periodically refresh battery + Wi-Fi status (when not in sensor view)."""
    while True:
        v = power.battery_voltage()
        p = power.battery_percent()
        wifi = "WiFi:ok" if network.is_connected() else "WiFi:--"
        logger.info(f"BAT {v:.2f}V ({p}%)  {wifi}")
        await asyncio.sleep(5)


async def main():
    logger.info("FlexGrid V3 startup")

    try:
        uos.stat('config')
    except OSError:
        logger.warn("No config folder — creating")
        uos.mkdir('config')

    settings = SettingsManager.load()
    logger.info(f"Settings: {settings}")

    # Boot up subsystems (each handles its own absence gracefully)
    power         = PowerManager()
    display       = DisplayManager()
    sensor_matrix = SensorMatrix()
    network       = NetworkManager(settings)
    menu          = MenuManager(display, network, power)

    # Splash
    display.text_screen([
        "OpenMuscle",
        "FlexGrid V3",
        f"BAT {power.battery_voltage():.2f}V",
        "Booting...",
    ])

    # Wi-Fi (non-fatal if it fails)
    try:
        await network.connect()
    except Exception as e:
        logger.error(f"Network: {e}")

    logger.info("Spawning async tasks")
    asyncio.create_task(sensor_loop(sensor_matrix, network, display,
                                    settings.get("scan_interval_ms", 100)))
    asyncio.create_task(menu_loop(menu))
    asyncio.create_task(status_loop(power, network, display))

    while True:
        await asyncio.sleep(1)
