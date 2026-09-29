import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("FOODI_DB", "foodi.db")
    feeder_mode: str = os.getenv("FOODI_FEEDER", "fake")  # "fake" | "ble"
    ble_address: str = os.getenv("FOODI_BLE_ADDRESS", "")
    max_portion_g: int = int(os.getenv("FOODI_MAX_PORTION_G", "200"))
    daily_max_g: int = int(os.getenv("FOODI_DAILY_MAX_G", "600"))


settings = Settings()
