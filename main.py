# main.py — OpenMuscle FlexGrid V3 entry point.
# Runs after boot.py. Any crash here still leaves REPL accessible.

import asyncio
import flexgrid
import logger

logger.info("Booting FlexGrid V3")
asyncio.run(flexgrid.main())
