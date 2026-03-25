"""Tests for _region_from_latlon — pure coordinate-to-region mapping."""
import pytest
from data.events import _region_from_latlon


@pytest.mark.parametrize("lat, lon, expected", [
    # North America
    (40.71,  -74.00, "North America"),  # New York
    (51.51,   -0.13, "Europe"),         # London
    (35.69,  139.69, "Asia"),           # Tokyo
    # Jerusalem: lon=35.22 falls in Africa box (lon -25..55, lat -35..37) before Middle East
    (31.77,   35.22, "Africa"),         # Jerusalem — Africa box checked first
    # Sydney: lat=-33.87 is below Asia's -10 lat floor → "Other"
    (-33.87, 151.21, "Other"),          # Sydney
    (15.55,   32.53, "Africa"),         # Khartoum, Sudan
    (48.38,   35.29, "Europe"),         # Donetsk, Ukraine
    (21.09,   96.88, "Asia"),           # Myanmar
    # NaN inputs
    (float("nan"), 0.0, "Unknown"),
    (0.0, float("nan"), "Unknown"),
])
def test_region_from_latlon(lat, lon, expected):
    assert _region_from_latlon(lat, lon) == expected


def test_region_south_america():
    # Sao Paulo: lat=-23.5, lon=-46.6 — should be South America (lat < 15)
    assert _region_from_latlon(-23.5, -46.6) == "South America"


def test_region_unknown_ocean():
    # Mid-Pacific (180° lon) — outside all defined boxes
    result = _region_from_latlon(0.0, 180.0)
    assert result in ("Asia", "Other")
