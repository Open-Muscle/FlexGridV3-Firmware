# boot.py — OpenMuscle FlexGrid V3
# 60-sensor 15x4 Velostat pressure matrix on ESP32-S3-WROOM-1-N16R8.
# Software v0.1.0

import sys
sys.path.append('/lib')

import asyncio
import flexgrid
import logger

logger.info("Booting FlexGrid V3")
asyncio.run(flexgrid.main())
