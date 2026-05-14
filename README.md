# FlexGrid V3 Firmware

MicroPython firmware for the **OpenMuscle FlexGrid V3** — a 60-sensor (15×4) Velostat pressure-matrix wearable controller built on the ESP32-S3-WROOM-1-N16R8.

Companion to the hardware repo: [OpenMuscle-FlexGrid](https://github.com/Open-Muscle/OpenMuscle-FlexGrid).

---

## Status

🟢 **v0.1.6 — bleed-free matrix scan.** Two boards brought up (2026-05-13). Scan runs ~75 Hz with a clean idle baseline, no row sneak, no scan-direction carryover, and isolated single-cell response under a single-column Velostat strip press test. UDP telemetry validated to the desktop web UI (`openmuscle web`). Remaining work: ICM-42688-P IMU driver, SCRN1 OLED on board #2, diagnose IO2/ROW_1 GPIO output anomaly on board #1, characterizing one occasionally-glitchy sensor.

### Version history

| Version | Scan rate | Change | Why |
|---------|-----------|--------|-----|
| v0.1.0 | n/a | initial port from V1 firmware | bring-up |
| v0.1.1 | 24 Hz | ground-other-rows + averaging | row sneak-path bleed |
| v0.1.2 | 139 Hz | row-outer scan, raw single-sample | speed + raw signal |
| v0.1.3 | 139 Hz | GC pacing, decoupled display, matrix reuse | GC pressure / slowdown |
| v0.1.4 | 139 Hz | UDP socket in `__init__`, no Wi-Fi-join race | silent UDP after slow join |
| v0.1.5 | 110 Hz | mux ENABLE-gated address writes + 5 µs row discharge | mux address glitches + carryover |
| **v0.1.6** | **75 Hz** | 30 µs discharge + discard-first-read | residual carryover from ADC sample-and-hold |

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

## Sensor scan techniques

Getting clean readings out of a 15×4 Velostat matrix on an ESP32-S3 took more work than expected. Each technique below addresses a specific failure mode we hit during V3 bring-up — keep these in mind when porting to a new board or revising the design.

### 1. Ground-other-rows (row sneak path)

When reading row R, drive all other rows as `OUTPUT LOW` rather than leaving them as `INPUT`. Without this, a press on (col K, row R) can lift the reading of (col K, row R') for any R' ≠ R, because the unselected mux columns are high-Z and Velostat can form sneak paths through pressed cells in other rows. The classic "whole row lights up from one press" symptom.

```python
def _set_row_mode(self, target_row):
    for i, p in enumerate(self.row_pins):
        if i == target_row:
            p.init(Pin.IN)
        else:
            p.init(Pin.OUT, value=0)
```

### 2. Mux ENABLE-gated address writes

`CD74HC4067` settles in ~80 ns, much faster than MicroPython's ~1 µs per `Pin.value()` call. Sequentially writing S0–S3 means the mux briefly routes intermediate addresses — e.g., the col 1 → col 2 transition goes `0001 → 0000 → 0010`, and during the `0000` window the mux drives col 0 (where the press is) to 3.3 V, kicking energy into the pressed cell *during* the address change.

The fix is to raise `E` (mux disable) before changing S0–S3 and lower it again after. While disabled, every channel is high-Z, so intermediate addresses don't get routed:

```python
def _select_column(self, channel):
    self.mux_en.value(1)              # disable
    self.S[0].value(channel & 0x1)
    self.S[1].value((channel >> 1) & 0x1)
    self.S[2].value((channel >> 2) & 0x1)
    self.S[3].value((channel >> 3) & 0x1)
    time.sleep_us(self.addr_settle_us)
    self.mux_en.value(0)              # re-enable
```

### 3. Active row discharge between columns

Even with ground-other-rows + mux gating, the row trace and ADC sample-and-hold cap can carry voltage from a pressed cell into the next column's read. The 10 kΩ pulldown isn't fast enough on its own against the combined trace + SAH capacitance. Before each ADC read, briefly drive the target row pin as `OUTPUT LOW` to actively drain it:

```python
p.init(Pin.OUT, value=0)
time.sleep_us(self.discharge_us)     # 30 µs needed empirically
p.init(Pin.IN)
```

### 4. Discard-first-read

Known MicroPython ESP32 ADC quirk: the first `ADC.read()` after a `Pin.init()` mode change can return a stale sample latched into the sample-and-hold cap *before* the transition. The fix is one wasted read:

```python
self.adc[row].read()             # discard
return self.adc[row].read()      # fresh sample
```

This was the missing piece that fully eliminated scan-direction bleed in v0.1.6.

### 5. Row-outer, col-inner scan order

For each row, set row mode once, then sweep all 15 columns. This means 4 `_set_row_mode` calls per scan instead of 60. The `Pin.init` cost is the largest per-step cost in the inner loop; minimizing it gets us most of the speedup from v0.1.1 (24 Hz) → v0.1.2 (139 Hz).

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
- **Press one cell, see a whole row light up:** Pre-v0.1.2 row sneak path. Fix is the ground-other-rows technique. If symptom persists on v0.1.2+, check the row pulldowns (R12–R15, 10 kΩ each) are populated and well-soldered.
- **Right-direction bleed when pressing one cell:** ADC sample-and-hold carryover. Fixed in v0.1.6 via the discard-first-read trick + 30 µs row discharge. If you see it return, lengthen `discharge_us` further or `avg_samples=2`.
- **Specific GPIO can't drive HIGH (reads near 0 when set to `Pin.OUT(1)`):** Verify the corresponding pulldown resistor is the spec value and not shorted. We saw this on board #1's IO2 (= ROW_1); other rows on the same board drove HIGH normally.
- **`Pin.init(Pin.OUT, value=0)` doesn't drive an ADC pin low quickly:** ESP32-S3 ADC1 pins (GPIO1–10) share an analog mux with the SAR. The first `ADC.read()` after a Pin mode change may return a stale sample. Use the discard-first-read trick (call `.read()` once and throw it away, then read again).

## License

MIT. See [LICENSE](LICENSE).

Part of the [OpenMuscle](https://github.com/Open-Muscle) ecosystem.
