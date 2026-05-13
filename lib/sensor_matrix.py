# lib/sensor_matrix.py
# 15-column x 4-row Velostat sensor matrix on the V3 flex PCB.
#
# v0.1.2: row-outer, col-inner scan. Reconfigure row pin modes once per
#         row (4x per scan) rather than per cell (60x per scan).
#         Defaults: settle_us=20 (plenty for 10k * ~50pF), avg_samples=1
#         (closest to raw). Bump avg_samples if you want noise floor lower.

from machine import Pin, ADC
import time
import pinmap


class SensorMatrix:
    def __init__(self, attenuation=ADC.ATTN_11DB, settle_us=20, avg_samples=1):
        # 4-bit MUX address lines (CD74HC4067)
        self.S = [
            Pin(pinmap.MUX_S0, Pin.OUT),
            Pin(pinmap.MUX_S1, Pin.OUT),
            Pin(pinmap.MUX_S2, Pin.OUT),
            Pin(pinmap.MUX_S3, Pin.OUT),
        ]
        self.mux_en = Pin(pinmap.MUX_EN, Pin.OUT, value=0)  # active LOW = enable

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

        # Pre-allocated matrix; reused across scans to avoid GC pressure.
        self.matrix = [[0] * self.num_rows for _ in range(self.num_cols)]

    def _select_column(self, channel):
        self.S[0].value(channel & 0x1)
        self.S[1].value((channel >> 1) & 0x1)
        self.S[2].value((channel >> 2) & 0x1)
        self.S[3].value((channel >> 3) & 0x1)

    def _set_row_mode(self, target_row):
        """target_row = INPUT (ADC), all others = OUTPUT LOW (sneak-path shunt)."""
        for i, p in enumerate(self.row_pins):
            if i == target_row:
                p.init(Pin.IN)
            else:
                p.init(Pin.OUT, value=0)

    def _read(self, row):
        if self.avg_samples <= 1:
            return self.adc[row].read()
        s = 0
        for _ in range(self.avg_samples):
            s += self.adc[row].read()
        return s // self.avg_samples

    def scan_matrix(self):
        """
        Row-outer, col-inner scan. Returns the same pre-allocated list each
        time -- callers must read it immediately, not stash references.
        Holds non-target rows at GND while reading target row -> kills row sneak.
        """
        m = self.matrix
        settle = self.settle_us
        for row in range(self.num_rows):
            self._set_row_mode(row)
            for col in range(self.num_cols):
                self._select_column(col)
                time.sleep_us(settle)
                m[col][row] = self._read(row)
        # Park rows as inputs so external code can read ADCs freely.
        for p in self.row_pins:
            p.init(Pin.IN)
        return m
