# FlexGrid V3 Firmware

MicroPython firmware for the **OpenMuscle FlexGrid V3** — a 60-sensor (15×4) Velostat pressure-matrix wearable controller built on the ESP32-S3-WROOM-1-N16R8.

Companion to the hardware repo: [OpenMuscle-FlexGrid](https://github.com/Open-Muscle/OpenMuscle-FlexGrid).

---

## Status

🟢 **v0.1.4 — sensor pipeline validated.** Two boards bring-up complete (2026-05-13). Matrix scans clean at ~140 Hz with no row-bleed (ground-other-rows technique), idle baseline near zero, raw single-sample reads. UDP telemetry confirmed over Wi-Fi. Remaining work: ICM-42688-P IMU driver, SCRN1 OLED on board #2, characterizing one occasionally-glitchy sensor on board #1.

## What's new vs V1 firmware

| Aspect | V1 | V3 |
|--------|----|----|
| Matrix size | 16×4 (col 15 unused) | 15×4 (explicit) |
| OLED | SSD1306 128×64 | SSD1306 128×64 |
| Buttons | 2 (MENU, SELECT) | 3 software-readable (BOOT, MENU, SELECT) + RESET hardwired |
| Power | Always-on | MAX16054 soft-latch with `power_off()` |
| Battery monitor | none | ADC on `IO18` |
| IMU | none | ICM-42688-P over I²C (driver stub — TODO) |
| Pin map | hardcoded in modules | central `lib/pinmap.py` |

## Hardware requirements

- **OpenMuscle FlexGrid V3 rigid PCB** (ESP32-S3-WROOM-1-N16R8)
- **V3 flex PCB** with 15×4 Velostat matrix and Wurth 687120183722 FFC connector
- 1S LiPo battery (or USB power)

See [OpenMuscle-FlexGrid V3 README](https://github.com/Open-Muscle/OpenMuscle-FlexGrid/blob/main/KiCad/OM-FlexGrid%20V3/README.md) for the hardware build.

## Software requirements

- MicroPython **v1.28 or newer**, `ESP32_GENERIC_S3` build with **Octal SPIRAM support**
  - Direct download: <https://micropython.org/download/ESP32_GENERIC_S3/>
  - Look for `ESP32_GENERIC_S3-SPIRAM_OCT-*.bin`
- [`mpremote`](https://docs.micropython.org/en/latest/reference/mpremote.html) — for flashing and file transfer

## Flashing

1. **Install MicroPython** (one-time, per device):
   ```
   pip install --user esptool mpremote
   python -m esptool --chip esp32s3 --port COM<N> erase-flash
   python -m esptool --chip esp32s3 --port COM<N> --baud 460800 write-flash -z 0x0 ESP32_GENERIC_S3-SPIRAM_OCT-*.bin
   ```
2. **Install the SSD1306 driver** (one-time):
   ```
   mpremote connect COM<N> mip install ssd1306
   ```
3. **Copy this firmware to the device**:
   ```
   mpremote connect COM<N> cp -r lib :
   mpremote connect COM<N> cp boot.py :
   mpremote connect COM<N> cp flexgrid.py :
   ```
4. **Reset the board** and watch the splash on the OLED.

## Repository layout

```
boot.py              — entry point, starts the asyncio event loop
flexgrid.py          — main app: sensor loop, menu loop, status loop
lib/
├── pinmap.py        — central GPIO assignments (extracted from V3 KiCad schematic)
├── logger.py        — debug/info/warn/error
├── sensor_matrix.py — CD74HC4067 mux scan, 15 cols × 4 ADC rows
├── display_manager.py — SSD1306 128×64 heatmap + menu
├── menu_manager.py  — 3-button menu state machine
├── network_manager.py — Wi-Fi + UDP broadcast of matrix data
├── power_manager.py — Battery ADC, MAX16054 power-off latch
└── settings_manager.py — JSON config persistence
```

## Configuration

First boot creates `/config/settings.json` from defaults. Edit by hand or call `SettingsManager.save(d)` from the REPL.

```json
{
  "wifi_ssid": "OpenMuscle",
  "wifi_password": "3141592653",
  "udp_target_ip": "192.168.1.49",
  "udp_port": 3141,
  "scan_interval_ms": 100,
  "display_brightness": 255
}
```

## Visualizing the data

The host-side tooling lives in a separate repo: [Open-Muscle/OpenMuscle-Software](https://github.com/Open-Muscle/OpenMuscle-Software). It includes a UDP listener, live heatmap, capture-to-CSV, and ML training/inference pipelines.

```
git clone https://github.com/Open-Muscle/OpenMuscle-Software
cd OpenMuscle-Software/pc
pip install -e .
openmuscle receive    # live heatmap from any FlexGrid on the LAN
```

The first time you run `openmuscle receive` on Windows, the Defender Firewall will prompt to allow Python through. Click **Allow** for both Private and Public networks, otherwise inbound UDP from the board will be silently dropped.

## Troubleshooting

- **Stuck in download mode at boot:** BOOT button held / shorted. Power-cycle without pressing BOOT.
- **Display blank, "SSD1306 init failed" on REPL:** Run `import ssd1306` from the REPL to confirm the mip-installed driver is present. Re-run `mpremote mip install ssd1306` if missing.
- **`AttributeError: module 'asyncio' has no attribute ...`:** You're on an older MicroPython that uses `uasyncio`. Upgrade to v1.20+ or globally `import uasyncio as asyncio`.
- **Loud "USB connect" sound every 2 s on plug-in:** ESP32 cycling boot modes; can mean GPIO0 (BOOT) is being held low. Check the BOOT button for stuck closure / solder bridge.
- **WiFi shows connected but `openmuscle receive` sees nothing:** Windows Defender Firewall is dropping inbound UDP. Click **Allow** on the firewall prompt, or add an explicit rule: `New-NetFirewallRule -DisplayName "OpenMuscle UDP 3141" -Direction Inbound -Protocol UDP -LocalPort 3141 -Action Allow` (PowerShell, admin).
- **WiFi joins slowly / `udp_target_ip` was never reached:** Fixed in v0.1.4 — `NetworkManager` now creates the UDP socket in `__init__` instead of waiting on `connect()`, so a slow Wi-Fi join no longer leaves the sender permanently silent.

## License

MIT. See [LICENSE](LICENSE).

Part of the [OpenMuscle](https://github.com/Open-Muscle) ecosystem.
