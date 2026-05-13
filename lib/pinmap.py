# lib/pinmap.py
# Central GPIO assignments for the FlexGrid V3 rigid PCB.
# Extracted from the V3 KiCad schematic (OM-FlexGrid-Rigid-PCB).
# Update here, not in individual modules.

# Sensor matrix multiplexer (CD74HC4067)
MUX_S0 = 5
MUX_S1 = 6
MUX_S2 = 7
MUX_S3 = 15
MUX_EN = 16  # active LOW

# Sensor matrix ADC row inputs (10k pulldowns on board)
ADC_ROW_0 = 1
ADC_ROW_1 = 2
ADC_ROW_2 = 3
ADC_ROW_3 = 4

# I2C bus (OLED SSD1306 128x32, IMU ICM-42688-P)
I2C_SDA = 8
I2C_SCL = 9

# SPI bus (reserved — IMU can be moved here if I2C contended)
SPI_MISO = 11
SPI_SCK  = 12
SPI_MOSI = 13
SPI_CS   = 14

# User input buttons (active LOW, internal pull-up)
BTN_BOOT   = 0     # strap pin — also enters download mode at reset if held
BTN_SELECT = 10
BTN_MENU   = 21
# RESET button is hardwired to chip EN — not GPIO

# Power management
PWR_OFF  = 45      # drive HIGH momentarily to tell MAX16054 to drop power
ADC_BAT  = 18      # battery voltage divider

# Haptic motor (not populated on first V3 build — Q1 + D4 omitted)
MOT_SIG  = 17

# Auxiliary GPIOs broken out
AUX_40   = 40
AUX_41   = 41

# Sensor matrix dimensions
NUM_COLS = 15      # 15 active columns on the mux (channel 15 unused)
NUM_ROWS = 4
