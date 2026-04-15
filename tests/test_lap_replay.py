"""Focused tests for lap replay resolution and payload generation."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class FakeLapSeries(pd.Series):
    _metadata = ["_telemetry_map"]

    @property
    def _constructor(self):
        return FakeLapSeries

    def get_car_data(self):
        key = (self["Driver"], int(self["LapNumber"]))
        return self._telemetry_map[key]["car"].copy()

    def get_pos_data(self):
        key = (self["Driver"], int(self["LapNumber"]))
        return self._telemetry_map[key]["pos"].copy()


class FakeLapsFrame(pd.DataFrame):
    _metadata = ["_telemetry_map"]

    @property
    def _constructor(self):
        return FakeLapsFrame

    @property
    def _constructor_sliced(self):
        return FakeLapSeries

    def __finalize__(self, other, method=None, **kwargs):
        result = super().__finalize__(other, method=method, **kwargs)
        self._telemetry_map = getattr(other, "_telemetry_map", {})
        return result


class LapReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if "fastf1" not in sys.modules:
            fastf1_stub = types.ModuleType("fastf1")
            fastf1_stub.get_session = lambda *args, **kwargs: None
            sys.modules["fastf1"] = fastf1_stub

    def _build_session(self):
        telemetry_map = {
            ("VER", 3): {
                "car": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "36s", "72s"]),
                        "Speed": [140, 250, 160],
                        "Throttle": [40, 100, 55],
                        "Brake": [5, 0, 18],
                        "nGear": [3, 8, 4],
                    }
                ),
                "pos": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "36s", "72s"]),
                        "X": [0, 90, 180],
                        "Y": [0, 60, 0],
                    }
                ),
            },
            ("NOR", 8): {
                "car": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "35s", "70s"]),
                        "Speed": [138, 248, 158],
                        "Throttle": [42, 99, 57],
                        "Brake": [4, 0, 17],
                        "nGear": [3, 8, 4],
                    }
                ),
                "pos": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "35s", "70s"]),
                        "X": [0, 88, 180],
                        "Y": [0, 58, 0],
                    }
                ),
            },
        }
        laps = FakeLapsFrame(
            [
                {
                    "Driver": "VER",
                    "LapNumber": 3,
                    "LapTime": pd.to_timedelta("0 days 00:01:12"),
                    "LapTimeSeconds": 72.0,
                    "SessionPart": "Q3",
                    "Compound": "SOFT",
                    "PitOutTime": pd.NaT,
                    "PitInTime": pd.NaT,
                    "IsAccurate": True,
                    "Deleted": False,
                    "IsPersonalBest": True,
                },
                {
                    "Driver": "NOR",
                    "LapNumber": 8,
                    "LapTime": pd.to_timedelta("0 days 00:01:10"),
                    "LapTimeSeconds": 70.0,
                    "SessionPart": "Q3",
                    "Compound": "SOFT",
                    "PitOutTime": pd.NaT,
                    "PitInTime": pd.NaT,
                    "IsAccurate": True,
                    "Deleted": False,
                    "IsPersonalBest": True,
                },
            ]
        )
        laps._telemetry_map = telemetry_map
        return types.SimpleNamespace(
            laps=laps,
            results=pd.DataFrame(
                [
                    {"Abbreviation": "VER", "Q3": pd.to_timedelta("0 days 00:01:12")},
                    {"Abbreviation": "NOR", "Q3": pd.to_timedelta("0 days 00:01:10")},
                ]
            ),
            get_circuit_info=lambda: types.SimpleNamespace(
                corners=pd.DataFrame(
                    [
                        {"Number": 1, "Letter": "", "X": 0.0, "Y": 0.0},
                        {"Number": 2, "Letter": "", "X": 90.0, "Y": 60.0},
                    ]
                )
            ),
        )

    def test_compare_lap_replay_builds_modes_and_resolves_q3_selectors(self) -> None:
        lap_replay = __import__("f1_mcp.services.lap_replay", fromlist=["compare_lap_replay"])
        session = self._build_session()
        with patch.object(lap_replay, "load_session", return_value=session):
            result = lap_replay.compare_lap_replay(
                year=2025,
                race="Barcelona",
                session_type="Q",
                driver_code1="VER",
                driver_code2="NOR",
                lap_selector1="best_q3_lap",
                lap_selector2="best_q3_lap",
            )

        self.assertEqual(result["drivers"]["VER"]["lap_number"], 3)
        self.assertEqual(result["drivers"]["NOR"]["lap_number"], 8)
        self.assertIn("real_time", result["modes"])
        self.assertIn("equal_progress", result["modes"])
        self.assertEqual(result["modes"]["real_time"]["samples"][0]["cars"]["VER"]["speed"], 140)
        self.assertEqual(result["modes"]["equal_progress"]["samples"][-1]["cars"]["NOR"]["gear"], 4)
        self.assertTrue(result["circuit"]["corners"])

    def test_compare_lap_replay_supports_explicit_lap_number(self) -> None:
        lap_replay = __import__("f1_mcp.services.lap_replay", fromlist=["compare_lap_replay"])
        session = self._build_session()
        with patch.object(lap_replay, "load_session", return_value=session):
            result = lap_replay.compare_lap_replay(
                year=2025,
                race="Barcelona",
                session_type="Q",
                driver_code1="VER",
                driver_code2="NOR",
                lap_selector1="3",
                lap_selector2="8",
            )

        self.assertEqual(result["drivers"]["VER"]["selector"], "3")
        self.assertEqual(result["drivers"]["NOR"]["selector"], "8")
