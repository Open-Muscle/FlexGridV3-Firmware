# lib/power_manager.py
# Power management for V3: battery voltage monitoring + MAX16054 soft power-off.

from machine import Pin, ADC
import time
import pinmap
import logger


class PowerManager:
    # Divider on board: ADC_BAT pin sees Vbat * R_div_ratio
    # Adjust this constant if your divider is different (see schematic R7/R8).
    VBAT_DIVIDER = 2.0
    ADC_FULL_SCALE = 4095
    ADC_VREF = 3.3  # nominal at ATTN_11DB the usable range is ~0-3.1 V

    def __init__(self):
        self.bat_adc = ADC(Pin(pinmap.ADC_BAT))
        self.bat_adc.atten(ADC.ATTN_11DB)
        self.pwr_off = Pin(pinmap.PWR_OFF, Pin.OUT, value=0)

    def battery_raw(self):
        """Average of 8 samples to reduce noise."""
        s = 0
        for _ in range(8):
            s += self.bat_adc.read()
        return s // 8

    def battery_voltage(self):
        raw = self.battery_raw()
        return (raw / self.ADC_FULL_SCALE) * self.ADC_VREF * self.VBAT_DIVIDER

    def battery_percent(self):
        """Rough estimate for a 1S LiPo: 3.3V = 0%, 4.2V = 100%."""
        v = self.battery_voltage()
        pct = max(0, min(100, int((v - 3.3) / (4.2 - 3.3) * 100)))
        return pct

    def power_off(self):
        """Toggle the MAX16054 to drop the main rail. Goodbye, world."""
        logger.info("Power-off requested")
        # MAX16054 latch is released by a pulse on its KILL input.
        self.pwr_off.value(1)
        time.sleep_ms(200)
        self.pwr_off.value(0)
        # If we're still here after a few seconds, USB is keeping us alive.
        time.sleep(3)
        logger.warn("Still alive — likely USB-powered, latch can't drop rail")
