"""UNO Q Linux <-> MCU bridge stub.

On the real board use Arduino's Bridge (RPC) from App Lab. Verify the exact API in the
current Arduino docs; record the working calls here in Phase 0.
"""


class McuBridge:
    def read_sensor(self, name: str) -> float:  # pragma: no cover - hardware only
        raise NotImplementedError("Wire up Arduino Bridge in Phase 0/1")
