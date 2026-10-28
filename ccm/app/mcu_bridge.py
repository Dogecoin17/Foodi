"""UNO Q Linux <-> MCU bridge.

The MCU sketch (ccm/mcu/foodi_ccm_mcu) owns the fans and the physical LEDs;
it cools autonomously even if Linux hangs. This module only pushes status
(feeder / Wi-Fi connection LEDs) and reads back temperature and fan state.

Mode is selected with FOODI_MCU=bridge|off (default off). "off" is a no-op
so the backend runs unchanged on any laptop; "bridge" requires the Arduino
App Lab runtime on the UNO Q (arduino.app_utils is preinstalled there, not
pip-installable) and the foodi_ccm_mcu sketch flashed on the STM32.
"""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger(__name__)


class NullMcuBridge:
    """No-op used everywhere except the real CCM hardware."""

    available = False

    async def set_conn_leds(self, feeder: bool, wifi: bool) -> None:
        pass

    async def temperature(self) -> float | None:
        return None

    async def fan_on(self) -> bool | None:
        return None


class McuBridge(NullMcuBridge):
    """Talks to the UNO Q's STM32 over the Arduino Bridge (RPC)."""

    available = True

    def __init__(self) -> None:
        from arduino.app_utils import Bridge  # only exists on the UNO Q

        self._bridge = Bridge

    async def _call(self, method: str, *args):
        # Bridge.call is blocking; keep it off the event loop.
        return await asyncio.to_thread(self._bridge.call, method, *args)

    async def set_conn_leds(self, feeder: bool, wifi: bool) -> None:
        try:
            await self._call("set_conn_leds", feeder, wifi)
        except Exception as exc:
            log.warning("mcu set_conn_leds failed: %s", exc)

    async def temperature(self) -> float | None:
        try:
            t = await self._call("get_temp")
        except Exception as exc:
            log.warning("mcu get_temp failed: %s", exc)
            return None
        return float(t) if t == t else None  # NaN -> sensor fault

    async def fan_on(self) -> bool | None:
        try:
            return bool(await self._call("fan_on"))
        except Exception as exc:
            log.warning("mcu fan_on failed: %s", exc)
            return None


def make_mcu_bridge(mode: str) -> NullMcuBridge:
    if mode == "bridge":
        try:
            return McuBridge()
        except ImportError:
            log.warning("FOODI_MCU=bridge but arduino.app_utils is missing; running without MCU")
    return NullMcuBridge()
