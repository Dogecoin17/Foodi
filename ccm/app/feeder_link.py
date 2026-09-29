"""Feeder abstraction: FakeFeeder (simulator) and BleFeeder (real hardware, Phase 3)."""
from __future__ import annotations

import asyncio
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Awaitable, Callable

from . import protocol as P

Listener = Callable[[P.Message], Awaitable[None]]


class FeederLink(ABC):
    def __init__(self) -> None:
        self._listeners: list[Listener] = []
        self.connected = False

    def subscribe(self, cb: Listener) -> None:
        self._listeners.append(cb)

    async def _emit(self, msg: P.Message) -> None:
        for cb in self._listeners:
            await cb(msg)

    @abstractmethod
    async def start(self) -> None: ...
    @abstractmethod
    async def stop(self) -> None: ...
    @abstractmethod
    async def dispense(self, cmd_id: int, grams: int) -> None: ...
    @abstractmethod
    async def set_schedule(self, entries: list[tuple[int, int, int]]) -> None: ...
    @abstractmethod
    async def tare(self) -> None: ...


class FakeFeeder(FeederLink):
    """Simulates a feeder: hopper, bowl load cell, a pet that nibbles, and an autonomous schedule."""

    MAX_PORTION_G = 200

    def __init__(self, tick_s: float = 1.0) -> None:
        super().__init__()
        self.tick_s = tick_s
        self.hopper_g = 2000.0
        self.hopper_capacity_g = 2000.0
        self.bowl_g = 0.0
        self.schedule: list[tuple[int, int, int]] = []
        self.state = P.FeederState.IDLE
        self._seq = 0
        self._task: asyncio.Task | None = None
        self._seen: dict[int, int] = {}  # cmd_id -> actual_g (idempotency, finished)
        self._inflight: set[int] = set()  # cmd_ids currently dispensing
        self._sched_counter = 0
        self._last_minute = -1

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    async def start(self) -> None:
        self.connected = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self.connected = False
        if self._task:
            self._task.cancel()

    async def _loop(self) -> None:
        tick = 0
        while True:
            await asyncio.sleep(self.tick_s)
            tick += 1
            if self.bowl_g > 0 and random.random() < 0.3:  # the pet nibbles
                self.bowl_g = max(0.0, self.bowl_g - random.uniform(1, 5))
            await self._check_schedule()
            if tick % 2 == 0:
                await self._emit_telemetry()

    async def _check_schedule(self) -> None:
        now = datetime.now()
        minute = now.hour * 60 + now.minute
        if minute == self._last_minute:
            return
        self._last_minute = minute
        for m, grams, mask in self.schedule:
            if m == minute and mask & (1 << now.weekday()):
                self._sched_counter += 1
                await self._do_dispense(0x80000000 | self._sched_counter, grams)

    async def _emit_telemetry(self) -> None:
        pct = int(100 * self.hopper_g / self.hopper_capacity_g)
        if pct < 15:
            self.state = P.FeederState.LOW_FOOD
        elif self.state == P.FeederState.LOW_FOOD:
            self.state = P.FeederState.IDLE
        await self._emit(P.decode(P.encode_telemetry(self._next_seq(), int(self.bowl_g), pct, self.state)))

    async def _do_dispense(self, cmd_id: int, grams: int) -> None:
        if cmd_id in self._inflight:  # retry arrived mid-dispense: just re-ACK, never dispense twice
            await self._emit(P.decode(P.encode_ack(self._next_seq(), cmd_id)))
            return
        if cmd_id in self._seen:  # idempotent retry of a finished command
            await self._emit(P.decode(P.encode_dispensed(self._next_seq(), cmd_id, grams, self._seen[cmd_id])))
            return
        if grams > self.MAX_PORTION_G:
            await self._emit(P.decode(P.encode_nack(self._next_seq(), cmd_id, P.ErrorCode.OVER_LIMIT)))
            return
        if self.hopper_g < grams:
            await self._emit(P.decode(P.encode_nack(self._next_seq(), cmd_id, P.ErrorCode.EMPTY_HOPPER)))
            return
        self._inflight.add(cmd_id)
        await self._emit(P.decode(P.encode_ack(self._next_seq(), cmd_id)))
        self.state = P.FeederState.DISPENSING
        await asyncio.sleep(min(1.0, self.tick_s))
        actual = grams + random.randint(-2, 2)
        self.hopper_g -= actual
        self.bowl_g += actual
        self.state = P.FeederState.IDLE
        self._seen[cmd_id] = actual
        self._inflight.discard(cmd_id)
        await self._emit(P.decode(P.encode_dispensed(self._next_seq(), cmd_id, grams, actual)))

    async def dispense(self, cmd_id: int, grams: int) -> None:
        asyncio.create_task(self._do_dispense(cmd_id, grams))

    async def set_schedule(self, entries: list[tuple[int, int, int]]) -> None:
        self.schedule = list(entries)

    async def tare(self) -> None:
        self.bowl_g = 0.0


class BleFeeder(FeederLink):
    """Real feeder over BLE. UNTESTED SKELETON – finish in Phase 3 once firmware exists.

    TODO: reconnect with backoff, ACK timeout + retry (same cmd_id), SYNC_TIME + SET_SCHEDULE on connect.
    """

    SERVICE = "f00d0000-0000-4000-8000-00805f9b34fb"
    COMMAND = "f00d0001-0000-4000-8000-00805f9b34fb"
    EVENT = "f00d0002-0000-4000-8000-00805f9b34fb"
    TELEMETRY = "f00d0003-0000-4000-8000-00805f9b34fb"

    def __init__(self, address: str) -> None:
        super().__init__()
        self.address = address
        self._client = None
        self._seq = 0
        self._loop: asyncio.AbstractEventLoop | None = None

    def _next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    async def start(self) -> None:
        from bleak import BleakClient  # imported lazily so the simulator needs no BLE stack

        self._loop = asyncio.get_running_loop()
        self._client = BleakClient(self.address, disconnected_callback=self._on_disconnect)
        await self._client.connect()
        await self._client.start_notify(self.EVENT, self._on_notify)
        await self._client.start_notify(self.TELEMETRY, self._on_notify)
        self.connected = True
        await self._write(P.encode_sync_time(self._next_seq(), int(time.time()), 0))  # TODO: real tz offset

    async def stop(self) -> None:
        if self._client:
            await self._client.disconnect()
        self.connected = False

    def _on_disconnect(self, _client) -> None:
        self.connected = False  # TODO: schedule reconnect

    def _on_notify(self, _char, data: bytearray) -> None:
        try:
            msg = P.decode(bytes(data))
        except ValueError:
            return
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._emit(msg), self._loop)

    async def _write(self, packet: bytes) -> None:
        await self._client.write_gatt_char(self.COMMAND, packet, response=True)

    async def dispense(self, cmd_id: int, grams: int) -> None:
        await self._write(P.encode_dispense(self._next_seq(), cmd_id, grams))

    async def set_schedule(self, entries: list[tuple[int, int, int]]) -> None:
        await self._write(P.encode_set_schedule(self._next_seq(), entries))

    async def tare(self) -> None:
        await self._write(P.encode_tare(self._next_seq()))


def make_feeder(mode: str, ble_address: str = "") -> FeederLink:
    if mode == "ble":
        return BleFeeder(ble_address)
    return FakeFeeder()
