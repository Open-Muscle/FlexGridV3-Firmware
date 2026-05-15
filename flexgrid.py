# flexgrid.py
# OpenMuscle FlexGrid V3 — main application.

import asyncio
import gc
import machine
import time
import uos
import logger

from settings_manager import SettingsManager
from sensor_matrix    import SensorMatrix
from display_manager  import DisplayManager
from menu_manager     import MenuManager
from network_manager  import NetworkManager
from power_manager    import PowerManager


# Reset-cause names. ESP32-S3 MicroPython exposes the abstracted constants;
# brownout typically surfaces as PWRON_RESET (1) on this build, since the
# brownout detector reboots through the same path. If you see PWRON_RESET
# at an inconvenient time mid-recording, suspect a Wi-Fi-TX-burst brownout.
_RESET_CAUSES = {
    1: "POWER_ON",     # cold boot OR brownout on ESP32-S3
    2: "HARD",         # external RST line / chip enable
    3: "WDT",          # watchdog timeout -- task got stuck
    4: "DEEPSLEEP",
    5: "SOFT",         # Ctrl-D / machine.soft_reset()
    6: "BROWNOUT",     # some builds use this; treat as suspect
}


# Watchdog timeout in ms. Sensor_loop feeds it every iteration; if anything
# stalls the loop for longer than this, the WDT reboots the device. The
# subsequent boot logs reset_cause=WDT so we know what happened.
WDT_TIMEOUT_MS = 30_000


# Shared device-status dict, refreshed periodically by status_loop and
# attached as the `meta` field on every outgoing sensor packet. Keeping it
# at module scope means the 50 Hz sensor_loop just reads the dict (no ADC
# read, no lock) while the slow status_loop is the only writer.
device_status = {
    "vbat":         None,
    "pct":          None,
    "uptime_s":     0,
    "free_mem":     0,
    "rssi":         None,
    "imu":          None,   # placeholder; populated when ICM-42688-P is soldered
    # Reset diagnostics: populated once at boot, then carried in every
    # status broadcast so the PC sees them in the very first meta-bearing
    # packet of a new boot. If the PC observes reset_cause=WDT or
    # reset_cause_name=POWER_ON arriving mid-recording, that's a reboot
    # signature.
    "reset_cause":      None,
    "reset_cause_name": None,
}


# Shared watchdog handle so sensor_loop can feed it.
_wdt = None


def _feed_wdt():
    if _wdt is not None:
        try:
            _wdt.feed()
        except Exception:
            pass


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
    # Local err-rate-limiter: don't spam logs / persistent flash if every
    # iteration is failing (e.g. an unplugged sensor). Log first occurrence
    # and then 1-in-100 thereafter.
    err_count = 0
    while True:
        # Pet the watchdog FIRST so it's the first thing that stops
        # happening if this loop gets wedged.
        _feed_wdt()
        try:
            matrix = sensor_matrix.scan_matrix()
            n += 1
            meta = device_status if (n % meta_every == 0) else None
            await network.send_sensor(matrix, meta=meta)
            err_count = 0
        except Exception as e:
            if err_count == 0 or err_count % 100 == 0:
                logger.error("sensor_loop iter #{} failed: {}".format(err_count, e))
            err_count += 1
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
    # Open the on-flash log FIRST so everything that follows -- including
    # reset_cause, settings load, network init -- is persisted.
    logger.init_persistent()
    logger.info("FlexGrid V3 startup")

    # Reset cause: this tells us how the LAST run ended. PWRON could be
    # either a real cold boot OR a brownout, but it's still a useful signal
    # in combination with the recording's uptime_s telemetry.
    rc = None
    try:
        rc = machine.reset_cause()
        logger.info("Reset cause: {} ({})".format(rc, _RESET_CAUSES.get(rc, "?")))
    except Exception as e:
        logger.warn("Could not read reset_cause: {}".format(e))
    device_status["reset_cause"] = rc
    device_status["reset_cause_name"] = _RESET_CAUSES.get(rc, str(rc))

    try:
        uos.stat('config')
    except OSError:
        logger.warn("No config folder — creating")
        uos.mkdir('config')

    settings = SettingsManager.load()
    # Redact creds before logging (settings dict otherwise dumps wifi_password)
    redacted = {k: ("<redacted>" if k == "wifi_password" else v)
                for k, v in settings.items()}
    logger.info("Settings: {}".format(redacted))

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

    # Hardware watchdog: armed AFTER tasks are spawned so the slow
    # boot+WiFi phase doesn't trip it. Once armed, sensor_loop must call
    # _feed_wdt() within WDT_TIMEOUT_MS or the chip hard-resets and we
    # see reset_cause=WDT in the next boot's log.
    global _wdt
    try:
        _wdt = machine.WDT(timeout=WDT_TIMEOUT_MS)
        logger.info("Watchdog armed: {}ms".format(WDT_TIMEOUT_MS))
    except Exception as e:
        logger.warn("WDT init failed (may not be supported on this build): {}".format(e))

    while True:
        await asyncio.sleep(1)
