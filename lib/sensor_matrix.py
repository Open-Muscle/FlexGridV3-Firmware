# lib/sensor_matrix.py
# 15-column x 4-row Velostat sensor matrix on the V3 flex PCB.

from machine import Pin, ADC
import time
import pinmap


class SensorMatrix:
    def __init__(self, attenuation=ADC.ATTN_11DB, delay_us=100):
        # 4-bit MUX address lines
        self.S0 = Pin(pinmap.MUX_S0, Pin.OUT)
        self.S1 = Pin(pinmap.MUX_S1, Pin.OUT)
        self.S2 = Pin(pinmap.MUX_S2, Pin.OUT)
        self.S3 = Pin(pinmap.MUX_S3, Pin.OUT)
        self.mux_en = Pin(pinmap.MUX_EN, Pin.OUT)
        self.mux_en.value(0)  # active LOW = enable

        # 4 ADC row inputs
        adc_pins = (pinmap.ADC_ROW_0, pinmap.ADC_ROW_1,
                    pinmap.ADC_ROW_2, pinmap.ADC_ROW_3)
        self.adc = []
        for pin_num in adc_pins:
            adc = ADC(Pin(pin_num))
            adc.atten(attenuation)
            self.adc.append(adc)

        self.num_cols = pinmap.NUM_COLS
        self.num_rows = pinmap.NUM_ROWS
        self.delay_us = delay_us

    def _select_channel(self, channel):
        self.S0.value(channel & 0x1)
        self.S1.value((channel >> 1) & 0x1)
        self.S2.value((channel >> 2) & 0x1)
        self.S3.value((channel >> 3) & 0x1)

    def scan_matrix(self):
        """Scan all columns; return [[col0_row0..row3], [col1_row0..row3], ...]."""
        matrix = [[0] * self.num_rows for _ in range(self.num_cols)]
        for col in range(self.num_cols):
            self._select_channel(col)
            time.sleep_us(self.delay_us)
            for row in range(self.num_rows):
                matrix[col][row] = self.adc[row].read()
        return matrix
