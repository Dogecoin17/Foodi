import os
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    db_path: str = os.getenv("FOODI_DB", "foodi.db")
    feeder_mode: str = os.getenv("FOODI_FEEDER", "fake")  # "fake" | "ble" | "serial"
    ble_address: str = os.getenv("FOODI_BLE_ADDRESS", "")
    serial_port: str = os.getenv("FOODI_SERIAL_PORT", "")  # e.g. COM5 / /dev/ttyUSB0; empty = auto-detect
    mcu_mode: str = os.getenv("FOODI_MCU", "off")  # "bridge" on the UNO Q, "off" elsewhere
    # Live video source: MJPEG URL (phone/ESP32), camera index, or video file.
    # Empty = serve the pre-recorded clip at video_clip instead.
    video_url: str = os.getenv("FOODI_VIDEO_URL", "")
    video_clip: str = os.getenv("FOODI_VIDEO", str(_REPO_ROOT / "ai" / "results" / "cica1_roi.mp4"))
    video_model: str = os.getenv("FOODI_VIDEO_MODEL", str(_REPO_ROOT / "ai" / "yolox_nano.onnx"))
    # Scale display region in frame pixels: FOODI_SCALE_ROI=x1,y1,x2,y2 (empty = disabled)
    scale_roi: str = os.getenv("FOODI_SCALE_ROI", "")
    # inference threads: 0 = library default (all cores); set = pinned on constrained runs
    video_threads: int = int(os.getenv("FOODI_VIDEO_THREADS", "0"))
    max_portion_g: int = int(os.getenv("FOODI_MAX_PORTION_G", "200"))
    daily_max_g: int = int(os.getenv("FOODI_DAILY_MAX_G", "600"))


settings = Settings()
