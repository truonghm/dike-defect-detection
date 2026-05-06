"""Mappings and config loading for camera snapshot filenames."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from dike_defect_detection.camera_capture.constants import CAMERA_SITE_CONFIG_PATH


@dataclass(frozen=True, slots=True)
class CameraSite:
    """Metadata for one KBVISION snapshot endpoint.

    Parameters
    ----------
    camera_key: str
        Stable key used by scripts and CLI arguments.
    base_url: str
        Reachable camera web URL, excluding the snapshot path.
    site_code: str
        ASCII site abbreviation used in filenames.
    old_province_name: str
        Province name before the 2025 administrative changes.
    new_province_name: str
        Province name after the 2025 administrative changes.
    default_channel: int
        Default KBVISION channel to request from the snapshot endpoint.
    """

    camera_key: str
    base_url: str
    site_code: str
    old_province_name: str
    new_province_name: str
    default_channel: int = 1


OLD_PROVINCE_ABBR: dict[str, str] = {
    "An Giang": "AG",
    "Ba Ria - Vung Tau": "BV",
    "Bac Lieu": "BL",
    "Bac Kan": "BK",
    "Bac Giang": "BG",
    "Bac Ninh": "BN",
    "Ben Tre": "BT",
    "Binh Duong": "BD",
    "Binh Dinh": "BD",
    "Binh Phuoc": "BP",
    "Binh Thuan": "BTh",
    "Ca Mau": "CM",
    "Cao Bang": "CB",
    "Can Tho": "CT",
    "Da Nang": "DNa",
    "Dak Lak": "DL",
    "Dak Nong": "DNo",
    "Dien Bien": "DB",
    "Dong Nai": "DN",
    "Dong Thap": "DT",
    "Gia Lai": "GL",
    "Ha Giang": "HG",
    "Ha Nam": "HNa",
    "Ha Noi": "HN",
    "Ha Tinh": "HT",
    "Hai Duong": "HD",
    "Hai Phong": "HP",
    "Hau Giang": "HGi",
    "Hoa Binh": "HB",
    "Thanh pho Ho Chi Minh": "SG",
    "Hung Yen": "HY",
    "Khanh Hoa": "KH",
    "Kien Giang": "KG",
    "Kon Tum": "KT",
    "Lai Chau": "LC",
    "Lang Son": "LS",
    "Lao Cai": "LCa",
    "Lam Dong": "LD",
    "Long An": "LA",
    "Nam Dinh": "ND",
    "Nghe An": "NA",
    "Ninh Binh": "NB",
    "Ninh Thuan": "NT",
    "Phu Tho": "PT",
    "Phu Yen": "PY",
    "Quang Binh": "QB",
    "Quang Nam": "QNa",
    "Quang Ngai": "QNg",
    "Quang Ninh": "QN",
    "Quang Tri": "QT",
    "Soc Trang": "ST",
    "Son La": "SL",
    "Tay Ninh": "TN",
    "Thai Binh": "TB",
    "Thai Nguyen": "TNg",
    "Thanh Hoa": "TH",
    "Thua Thien Hue": "TTH",
    "Tien Giang": "TG",
    "Tra Vinh": "TV",
    "Tuyen Quang": "TQ",
    "Vinh Long": "VL",
    "Vinh Phuc": "VP",
    "Yen Bai": "YB",
}

NEW_PROVINCE_ABBR: dict[str, str] = {
    "An Giang": "AG",
    "Bac Ninh": "BN",
    "Ca Mau": "CM",
    "Cao Bang": "CB",
    "Can Tho": "CT",
    "Da Nang": "DNa",
    "Dak Lak": "DL",
    "Dien Bien": "DB",
    "Dong Nai": "DN",
    "Dong Thap": "DT",
    "Gia Lai": "GL",
    "Ha Noi": "HN",
    "Ha Tinh": "HT",
    "Hai Phong": "HP",
    "Thanh pho Ho Chi Minh": "SG",
    "Hue": "TTH",
    "Hung Yen": "HY",
    "Khanh Hoa": "KH",
    "Lai Chau": "LC",
    "Lang Son": "LS",
    "Lao Cai": "LCa",
    "Lam Dong": "LD",
    "Nghe An": "NA",
    "Ninh Binh": "NB",
    "Phu Tho": "PT",
    "Quang Ngai": "QNg",
    "Quang Ninh": "QN",
    "Quang Tri": "QT",
    "Son La": "SL",
    "Tay Ninh": "TN",
    "Thai Nguyen": "TNg",
    "Thanh Hoa": "TH",
    "Tuyen Quang": "TQ",
    "Vinh Long": "VL",
}


def _require_str(raw_site: Mapping[str, object], field_name: str, site_index: int) -> str:
    raw_value = raw_site.get(field_name)
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise ValueError(f"Site #{site_index} must define a non-empty string field: {field_name}")
    return raw_value.strip()


def _get_default_channel(raw_site: Mapping[str, object], site_index: int) -> int:
    raw_value = raw_site.get("default_channel", 1)
    if isinstance(raw_value, bool) or not isinstance(raw_value, int):
        raise ValueError(f"Site #{site_index} field default_channel must be an integer")
    if raw_value < 1:
        raise ValueError(f"Site #{site_index} field default_channel must be at least 1")
    return raw_value


def _parse_camera_site(raw_site: Mapping[str, object], site_index: int) -> CameraSite:
    camera_key = _require_str(raw_site, "camera_key", site_index)
    base_url = _require_str(raw_site, "base_url", site_index)
    site_code = _require_str(raw_site, "site_code", site_index)
    old_province_name = _require_str(raw_site, "old_province_name", site_index)
    new_province_name = _require_str(raw_site, "new_province_name", site_index)
    default_channel = _get_default_channel(raw_site, site_index)

    if old_province_name not in OLD_PROVINCE_ABBR:
        raise ValueError(f"Site {camera_key} has unknown old_province_name: {old_province_name}")
    if new_province_name not in NEW_PROVINCE_ABBR:
        raise ValueError(f"Site {camera_key} has unknown new_province_name: {new_province_name}")

    return CameraSite(
        camera_key=camera_key,
        base_url=base_url,
        site_code=site_code,
        old_province_name=old_province_name,
        new_province_name=new_province_name,
        default_channel=default_channel,
    )


def load_camera_sites(config_path: Path = CAMERA_SITE_CONFIG_PATH) -> dict[str, CameraSite]:
    """Load camera site metadata from a JSON config file.

    Parameters
    ----------
    config_path: Path
        JSON file containing a top-level ``sites`` list.

    Returns
    -------
    dict[str, CameraSite]
        Camera sites keyed by ``camera_key``.

    Raises
    ------
    ValueError
        If the config file is missing, invalid, or contains inconsistent site
        metadata.
    """

    try:
        raw_config: object = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError(f"Camera site config not found: {config_path}") from error
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in camera site config {config_path}: {error.msg}") from error

    if not isinstance(raw_config, dict):
        raise ValueError(f"Camera site config must contain a JSON object: {config_path}")

    raw_sites = raw_config.get("sites")
    if not isinstance(raw_sites, list):
        raise ValueError(f"Camera site config must contain a top-level sites list: {config_path}")

    camera_sites: dict[str, CameraSite] = {}
    for site_index, raw_site in enumerate(raw_sites, start=1):
        if not isinstance(raw_site, dict):
            raise ValueError(f"Site #{site_index} must be a JSON object")
        camera_site = _parse_camera_site(cast(Mapping[str, object], raw_site), site_index)
        if camera_site.camera_key in camera_sites:
            raise ValueError(f"Duplicate camera_key in site config: {camera_site.camera_key}")
        camera_sites[camera_site.camera_key] = camera_site

    if not camera_sites:
        raise ValueError(f"Camera site config must define at least one site: {config_path}")
    return camera_sites


def get_camera_filename_prefix(
    camera_key: str,
    *,
    camera_sites: Mapping[str, CameraSite] | None = None,
    old_province_abbr: bool = True,
) -> str:
    """Return the `<province>-<site>` filename prefix for a camera.

    Parameters
    ----------
    camera_key: str
        Key in the camera site config.
    camera_sites: Mapping[str, CameraSite] | None
        In-memory camera site mapping. If omitted, the default config file is
        loaded.
    old_province_abbr: bool
        Whether to use the old province abbreviation table. If ``False``, use
        the current province abbreviation table.

    Returns
    -------
    str
        Filename prefix using normalized ASCII abbreviations.

    Examples
    --------
    >>> get_camera_filename_prefix("ketanthanh")
    'TB-KTT'
    >>> get_camera_filename_prefix("ketanthanh", old_province_abbr=False)
    'HY-KTT'
    """

    resolved_camera_sites = load_camera_sites() if camera_sites is None else camera_sites
    camera_site = resolved_camera_sites[camera_key]
    province_name = camera_site.old_province_name if old_province_abbr else camera_site.new_province_name
    province_abbr = OLD_PROVINCE_ABBR[province_name] if old_province_abbr else NEW_PROVINCE_ABBR[province_name]
    return f"{province_abbr}-{camera_site.site_code}"
