"""Focused tests for lap replay resolution, telemetry selection, and widget rendering."""

from __future__ import annotations

import importlib
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

    def _telemetry_for_self(self):
        key = (self["Driver"], int(self["LapNumber"]))
        return self._telemetry_map[key]

    def get_car_data(self):
        return self._telemetry_for_self().get("car", pd.DataFrame()).copy()

    def get_pos_data(self):
        return self._telemetry_for_self().get("pos", pd.DataFrame()).copy()

    def get_telemetry(self):
        return self._telemetry_for_self().get("telemetry", pd.DataFrame()).copy()


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

    def _build_session(self, telemetry_map: dict | None = None):
        telemetry_map = telemetry_map or {
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
        lap_replay = importlib.import_module("f1_mcp.services.lap_replay")
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
        self.assertEqual(result["drivers"]["VER"]["telemetry_status"]["speed"], "ok")
        self.assertTrue(result["circuit"]["corners"])

    def test_compare_lap_replay_supports_explicit_lap_number(self) -> None:
        lap_replay = importlib.import_module("f1_mcp.services.lap_replay")
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

    def test_choose_best_telemetry_source_prefers_complete_combined_telemetry(self) -> None:
        lap_replay = importlib.import_module("f1_mcp.services.lap_replay")
        telemetry_map = {
            ("VER", 3): {
                "car": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "10s", "20s"]),
                        "Speed": [120, 140, 160],
                    }
                ),
                "pos": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "10s", "20s"]),
                        "X": [0, 10, 20],
                        "Y": [0, 5, 0],
                    }
                ),
                "telemetry": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "10s", "20s"]),
                        "X": [0, 10, 20],
                        "Y": [0, 5, 0],
                        "Speed": [130, 180, 170],
                        "Throttle": [30, 90, 70],
                        "Brake": [0, 2, 8],
                        "nGear": [3, 7, 4],
                    }
                ),
            }
        }
        session = self._build_session(telemetry_map={**telemetry_map, ("NOR", 8): self._build_session().laps._telemetry_map[("NOR", 8)]})
        lap = session.laps[session.laps["Driver"] == "VER"].iloc[0]
        telemetry, source_name, field_status, debug_meta = lap_replay._choose_best_telemetry_source(lap)

        self.assertEqual(source_name, "get_telemetry fallback")
        self.assertEqual(field_status["throttle"], "ok")
        self.assertEqual(debug_meta["telemetry_time_min"], 0.0)
        self.assertEqual(int(telemetry["speed"].iloc[1]), 180)

    def test_choose_best_telemetry_source_uses_merge_path_when_valid(self) -> None:
        lap_replay = importlib.import_module("f1_mcp.services.lap_replay")
        session = self._build_session()
        lap = session.laps[session.laps["Driver"] == "VER"].iloc[0]
        telemetry, source_name, field_status, _ = lap_replay._choose_best_telemetry_source(lap)

        self.assertEqual(source_name, "merged car+position")
        self.assertEqual(field_status["speed"], "ok")
        self.assertEqual(field_status["x"], "ok")
        self.assertEqual(int(telemetry["gear"].iloc[-1]), 4)

    def test_missing_field_is_not_silently_zero_filled(self) -> None:
        lap_replay = importlib.import_module("f1_mcp.services.lap_replay")
        telemetry_map = {
            ("VER", 3): {
                "car": pd.DataFrame(
                    {
                        "Time": pd.to_timedelta(["0s", "36s", "72s"]),
                        "Speed": [140, 250, 160],
                        "Throttle": [40, 100, 55],
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
            ("NOR", 8): self._build_session().laps._telemetry_map[("NOR", 8)],
        }
        session = self._build_session(telemetry_map)
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

        ver_status = result["drivers"]["VER"]["telemetry_status"]
        ver_first_sample = result["modes"]["real_time"]["samples"][0]["cars"]["VER"]
        self.assertEqual(ver_status["brake"], "missing")
        self.assertIsNone(ver_first_sample["brake"])

    def test_widget_renders_unavailable_telemetry_as_dash(self) -> None:
        widget = importlib.import_module("f1_mcp.rendering.lap_replay_widget")
        html = widget.render_lap_replay_widget(
            {
                "title": "Replay",
                "subtitle": "Test",
                "mode_default": "real_time",
                "drivers": {
                    "VER": {
                        "driver_code": "VER",
                        "selector_label": "Lap 3",
                        "lap_number": 3,
                        "lap_time_seconds": 70.0,
                        "color": "#f00",
                        "telemetry_status": {"speed": "missing", "throttle": "ok", "brake": "missing", "gear": "missing"},
                    },
                    "NOR": {
                        "driver_code": "NOR",
                        "selector_label": "Lap 8",
                        "lap_number": 8,
                        "lap_time_seconds": 71.0,
                        "color": "#00f",
                        "telemetry_status": {"speed": "ok", "throttle": "ok", "brake": "ok", "gear": "ok"},
                    },
                },
                "circuit": {"view_box": [0, 0, 10, 10], "path": [{"x": 0, "y": 0}, {"x": 10, "y": 10}], "corners": []},
                "modes": {"real_time": {"duration_seconds": 1.0, "initial_time_seconds": 0.2, "samples": []}},
            }
        )

        self.assertIn("Missing telemetry: Speed, Brake, Gear", html)
        self.assertIn('data-field="speed">—</strong>', html)

    def test_initial_time_prefers_first_meaningful_sample(self) -> None:
        lap_replay = importlib.import_module("f1_mcp.services.lap_replay")
        samples = [
            {"t": 0.0, "cars": {"VER": {"speed": None, "throttle": None, "brake": None, "gear": None}}},
            {"t": 0.4, "cars": {"VER": {"speed": 0, "throttle": None, "brake": None, "gear": None}}},
            {"t": 0.8, "cars": {"VER": {"speed": 150, "throttle": 80, "brake": 0, "gear": 7}}},
        ]
        self.assertEqual(lap_replay._find_meaningful_initial_time(samples), 0.8)
