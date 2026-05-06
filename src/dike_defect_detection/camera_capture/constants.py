"""Constants for camera snapshot capture."""

from pathlib import Path

CAMERA_USERNAME_ENV_VAR = "CAMERA_USERNAME"
CAMERA_PASSWORD_ENV_VAR = "CAMERA_PASSWORD"

OUTPUT_DIR = Path("data/camera_img")
LOG_FILENAME = "camera_capture_log.csv"
CAMERA_SITE_CONFIG_PATH = Path("config/camera_sites.json")
USE_OLD_PROVINCE_ABBR = True
TIMEOUT_SECONDS = 5.0
CAPTURE_WORKERS = 16
RETRY_ATTEMPTS = 0
RETRY_WAIT_MULTIPLIER_SECONDS = 1.0
RETRY_WAIT_MIN_SECONDS = 1.0
RETRY_WAIT_MAX_SECONDS = 8.0

SNAPSHOT_PATH = "cgi-bin/snapshot.cgi"
USER_AGENT = "disaster-monitoring-ai-camera-capture/0.1"
