# lib/sensor_matrix.py
# 15-column x 4-row Velostat sensor matrix on the V3 flex PCB.
#
# v0.1.1: ground-other-rows scan to suppress the row sneak path.
#         Reading row r holds the other 3 rows as OUTPUT LOW so they can't
#         act as sneak return paths through pressed cells in adjacent rows.
#         Adds 4-sample ADC averaging and a longer mux settle.

from machine import Pin, ADC
import time
import pinmap


class SensorMatrix:
    def __init__(self, attenuation=ADC.ATTN_11DB, settle_us=300, avg_samples=4):
        # 4-bit MUX address lines (CD74HC4067)
        self.S = [
            Pin(pinmap.MUX_S0, Pin.OUT),
            Pin(pinmap.MUX_S1, Pin.OUT),
            Pin(pinmap.MUX_S2, Pin.OUT),
            Pin(pinmap.MUX_S3, Pin.OUT),
        ]
        self.mux_en = Pin(pinmap.MUX_EN, Pin.OUT, value=0)  # active LOW = enable

        # Row pins — used as Pin for driving LOW, ADC for reading.
        self._row_nums = (pinmap.ADC_ROW_0, pinmap.ADC_ROW_1,
                          pinmap.ADC_ROW_2, pinmap.ADC_ROW_3)
        self.row_pins = [Pin(n, Pin.IN) for n in self._row_nums]
        self.adc = []
        for n in self._row_nums:
            a = ADC(Pin(n))
            a.atten(attenuation)
            self.adc.append(a)

        self.num_cols = pinmap.NUM_COLS
        self.num_rows = pinmap.NUM_ROWS
        self.settle_us = settle_us
        self.avg_samples = avg_samples

    def _select_column(self, channel):
        self.S[0].value(channel & 0x1)
        self.S[1].value((channel >> 1) & 0x1)
        self.S[2].value((channel >> 2) & 0x1)
        self.S[3].value((channel >> 3) & 0x1)

    def _set_row_mode(self, target_row):
        """Configure target_row as INPUT (for ADC), all other rows as OUTPUT LOW."""
        for i, p in enumerate(self.row_pins):
            if i == target_row:
                p.init(Pin.IN)
            else:
                p.init(Pin.OUT)
                p.value(0)

    def _read_avg(self, row):
        n = self.avg_samples
        s = 0
        for _ in range(n):
            s += self.adc[row].read()
        return s // n

    def scan_matrix(self):
        """
        Returns [cols][rows] = [[col0_row0..row3], [col1_row0..row3], ...].
        Each cell is read with the other three rows actively held at GND.
        """
        m = [[0] * self.num_rows for _ in range(self.num_cols)]
        for col in range(self.num_cols):
            self._select_column(col)
            for row in range(self.num_rows):
                self._set_row_mode(row)
                time.sleep_us(self.settle_us)
                m[col][row] = self._read_avg(row)
        # Leave all rows as inputs so other code can read ADCs ad-hoc.
        for p in self.row_pins:
            p.init(Pin.IN)
        return m
