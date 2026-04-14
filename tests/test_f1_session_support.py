"""Focused tests for session-aware F1 MCP behavior."""

from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


class SessionProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._fastf1_backup = sys.modules.get("fastf1")
        fastf1_stub = types.ModuleType("fastf1")
        fastf1_stub.get_session = lambda *args, **kwargs: None
        sys.modules["fastf1"] = fastf1_stub
        sys.modules.pop("f1_mcp.providers.session_provider", None)
        self.session_provider = importlib.import_module("f1_mcp.providers.session_provider")

    def tearDown(self) -> None:
        if self._fastf1_backup is None:
            sys.modules.pop("fastf1", None)
        else:
            sys.modules["fastf1"] = self._fastf1_backup

    def test_normalize_session_aliases(self) -> None:
        cases = {
            None: "R",
            "race": "R",
            "qualifying": "Q",
            "quali": "Q",
            "q3": "Q",
            "sprint": "S",
            "sprint qualifying": "SQ",
            "sprint shootout": "SQ",
            "fp2": "FP2",
            "practice 3": "FP3",
        }
        for raw_value, expected in cases.items():
            with self.subTest(raw_value=raw_value):
                self.assertEqual(self.session_provider.normalize_session_type(raw_value), expected)

    def test_invalid_session_type_error_payload(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            self.session_provider.normalize_session_type("xyz")
        self.assertIn("Unsupported session_type 'xyz'", str(ctx.exception))
        self.assertIn("R, Q, SQ, S, FP1, FP2, FP3", str(ctx.exception))

    def test_is_qualifying_session_type(self) -> None:
        self.assertTrue(self.session_provider.is_qualifying_session_type("Q"))
        self.assertTrue(self.session_provider.is_qualifying_session_type("sprint shootout"))
        self.assertFalse(self.session_provider.is_qualifying_session_type("R"))


class QualifyingAnalysisTests(unittest.TestCase):
    def test_build_qualifying_runs_payload_classifies_out_push_cool_in(self) -> None:
        import pandas as pd

        qualifying_analysis = importlib.import_module("f1_mcp.services.qualifying_analysis")

        laps = pd.DataFrame(
            [
                {
                    "Driver": "VER",
                    "LapNumber": 1,
                    "LapTime": pd.to_timedelta("0 days 00:01:40"),
                    "LapTimeSeconds": 100.0,
                    "Compound": "SOFT",
                    "PitOutTime": pd.to_timedelta("0 days 00:00:05"),
                    "PitInTime": pd.NaT,
                    "IsAccurate": True,
                    "IsPersonalBest": False,
                    "TrackStatus": "1",
                    "Deleted": False,
                    "Time": pd.to_timedelta("0 days 00:05:00"),
                    "SessionPart": "Q1",
                },
                {
                    "Driver": "VER",
                    "LapNumber": 2,
                    "LapTime": pd.to_timedelta("0 days 00:01:31"),
                    "LapTimeSeconds": 91.0,
                    "Compound": "SOFT",
                    "PitOutTime": pd.NaT,
                    "PitInTime": pd.NaT,
                    "IsAccurate": True,
                    "IsPersonalBest": False,
                    "TrackStatus": "1",
                    "Deleted": False,
                    "Time": pd.to_timedelta("0 days 00:06:40"),
                    "SessionPart": "Q1",
                },
                {
                    "Driver": "VER",
                    "LapNumber": 3,
                    "LapTime": pd.to_timedelta("0 days 00:01:35"),
                    "LapTimeSeconds": 95.0,
                    "Compound": "SOFT",
                    "PitOutTime": pd.NaT,
                    "PitInTime": pd.NaT,
                    "IsAccurate": True,
                    "IsPersonalBest": False,
                    "TrackStatus": "1",
                    "Deleted": False,
                    "Time": pd.to_timedelta("0 days 00:08:20"),
                    "SessionPart": "Q1",
                },
                {
                    "Driver": "VER",
                    "LapNumber": 4,
                    "LapTime": pd.to_timedelta("0 days 00:01:29"),
                    "LapTimeSeconds": 89.0,
                    "Compound": "SOFT",
                    "PitOutTime": pd.NaT,
                    "PitInTime": pd.to_timedelta("0 days 00:09:50"),
                    "IsAccurate": True,
                    "IsPersonalBest": True,
                    "TrackStatus": "1",
                    "Deleted": False,
                    "Time": pd.to_timedelta("0 days 00:09:50"),
                    "SessionPart": "Q1",
                },
            ]
        )

        session = types.SimpleNamespace(
            results=pd.DataFrame([{"Abbreviation": "VER", "Q1": pd.to_timedelta("0 days 00:01:29")}])
        )
        result = qualifying_analysis.build_qualifying_runs_payload(session, "VER", laps, "Q")

        self.assertEqual(result["segments"][0]["name"], "Q1")
        run = result["segments"][0]["runs"][0]
        self.assertEqual([lap["lap_type"] for lap in run["laps"]], ["OUT", "PUSH", "COOL", "IN"])
        self.assertEqual(run["best_valid_push_lap_seconds"], 91.0)

    def test_compare_qualifying_payloads_summarizes_push_only_metrics(self) -> None:
        qualifying_analysis = importlib.import_module("f1_mcp.services.qualifying_analysis")

        driver1 = {
            "session_type": "Q",
            "driver_code": "VER",
            "segments": [
                {
                    "name": "Q1",
                    "best_valid_lap_seconds": 90.0,
                    "runs": [
                        {
                            "run_number": 1,
                            "laps": [
                                {"lap_number": 1, "lap_type": "OUT", "lap_time_seconds": 99.0, "is_valid": True, "is_personal_best": False, "is_deleted": False},
                                {"lap_number": 2, "lap_type": "PUSH", "lap_time_seconds": 91.0, "is_valid": True, "is_personal_best": False, "is_deleted": False},
                                {"lap_number": 3, "lap_type": "PUSH", "lap_time_seconds": 90.0, "is_valid": True, "is_personal_best": True, "is_deleted": False},
                                {"lap_number": 4, "lap_type": "ABORTED", "lap_time_seconds": None, "is_valid": False, "is_personal_best": False, "is_deleted": True},
                            ],
                        }
                    ],
                }
            ],
        }
        driver2 = {
            "session_type": "Q",
            "driver_code": "NOR",
            "segments": [
                {
                    "name": "Q1",
                    "best_valid_lap_seconds": 89.5,
                    "runs": [
                        {
                            "run_number": 1,
                            "laps": [
                                {"lap_number": 1, "lap_type": "OUT", "lap_time_seconds": 100.0, "is_valid": True, "is_personal_best": False, "is_deleted": False},
                                {"lap_number": 2, "lap_type": "PUSH", "lap_time_seconds": 90.8, "is_valid": True, "is_personal_best": False, "is_deleted": False},
                                {"lap_number": 3, "lap_type": "PUSH", "lap_time_seconds": 89.5, "is_valid": True, "is_personal_best": True, "is_deleted": False},
                            ],
                        }
                    ],
                }
            ],
        }

        result = qualifying_analysis.compare_qualifying_payloads(driver1, driver2)
        self.assertEqual(result["best_overall_qualifying_lap"]["VER"], 90.0)
        self.assertEqual(result["best_overall_qualifying_lap"]["NOR"], 89.5)
        self.assertEqual(result["valid_push_lap_counts"]["VER"], 2)
        self.assertEqual(result["invalid_deleted_aborted_attempt_counts"]["VER"]["aborted_laps"], 1)


class ToolLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if "fastf1" not in sys.modules:
            fastf1_stub = types.ModuleType("fastf1")
            fastf1_stub.get_session = lambda *args, **kwargs: None
            fastf1_stub.get_event_schedule = lambda *args, **kwargs: None
            sys.modules["fastf1"] = fastf1_stub

    def test_get_f1_results_normalizes_and_returns_session_type(self) -> None:
        reference_tools = importlib.import_module("f1_mcp.tools.reference_tools")

        class Session:
            def __init__(self) -> None:
                self.results = types.SimpleNamespace(
                    empty=False,
                    columns=["BroadcastName", "TeamName", "Position"],
                )

        class FakeResultsFrame:
            columns = ["BroadcastName", "TeamName", "Position"]
            empty = False

            def __getitem__(self, _cols):
                return self

            def sort_values(self, by=None, ascending=True):
                return self

            def copy(self):
                return self

            def to_dict(self, orient):
                return [{"BroadcastName": "L NORRIS", "TeamName": "McLaren", "Position": 1}]

        session = Session()
        session.results = FakeResultsFrame()

        with patch.object(reference_tools, "load_session", return_value=session) as load_session:
            result = reference_tools.get_f1_results(2025, "Monza", session_type="qualifying")

        load_session.assert_called_once_with(2025, "Monza", "Q")
        self.assertEqual(result["session_type"], "Q")
        self.assertEqual(result["results"][0]["Position"], 1)

    def test_get_driver_lap_times_forwards_normalized_session_type(self) -> None:
        import pandas as pd

        analysis_tools = importlib.import_module("f1_mcp.tools.analysis_tools")
        fake_df = pd.DataFrame(
            [
                {
                    "LapNumber": 1,
                    "LapTime": pd.to_timedelta("0 days 00:01:20"),
                    "LapTimeSeconds": 80.0,
                    "Compound": "SOFT",
                    "PitInTime": pd.NaT,
                    "PitOutTime": pd.NaT,
                }
            ]
        )

        with patch.object(analysis_tools, "get_driver_laps_df", return_value=fake_df) as get_driver_laps_df:
            result = analysis_tools.get_driver_lap_times(2025, "Bahrain", "VER", session_type="practice 2")

        get_driver_laps_df.assert_called_once_with(2025, "Bahrain", "FP2", "VER")
        self.assertEqual(result["session_type"], "FP2")
        self.assertEqual(len(result["lap_data"]), 1)

    def test_invalid_session_type_handled_cleanly(self) -> None:
        analysis_tools = importlib.import_module("f1_mcp.tools.analysis_tools")
        result = analysis_tools.get_driver_lap_times(2025, "Bahrain", "VER", session_type="XYZ")
        self.assertEqual(
            result["error"],
            "Unsupported session_type 'XYZ'. Use one of: R, Q, SQ, S, FP1, FP2, FP3.",
        )

    def test_compare_driver_lap_times_happy_path_qualifying(self) -> None:
        analysis_tools = importlib.import_module("f1_mcp.tools.analysis_tools")
        driver_payload = {
            "lap_data": [
                {
                    "LapNumber": 1,
                    "LapTime": "0 days 00:01:20",
                    "LapTimeSeconds": 80.0,
                    "Compound": "SOFT",
                    "PitInTime": "NaT",
                    "PitOutTime": "NaT",
                }
            ],
            "summary": {},
            "stints": [],
            "session_type": "Q",
        }
        with patch.object(analysis_tools, "get_driver_lap_times", side_effect=[driver_payload, driver_payload]):
            with patch.object(analysis_tools, "render_comparison_lap_plot", return_value="<img />"):
                result = analysis_tools.compare_driver_lap_times(
                    2025,
                    "Monza",
                    "NOR",
                    "LEC",
                    session_type="qualifying",
                )

        self.assertEqual(result["session_type"], "Q")
        self.assertEqual(result["comparison_summary"]["session_type"], "Q")
        self.assertIn("plot_html", result)

    def test_compare_qualifying_runs_uses_new_payload(self) -> None:
        analysis_tools = importlib.import_module("f1_mcp.tools.analysis_tools")
        qualifying_payload = {
            "session_type": "Q",
            "driver_code": "VER",
            "segments": [],
        }

        with patch.object(analysis_tools, "analyze_qualifying_runs", side_effect=[qualifying_payload, {**qualifying_payload, "driver_code": "NOR"}]):
            result = analysis_tools.compare_qualifying_runs(
                2025,
                "Bahrain",
                "VER",
                "NOR",
                session_type="Q",
            )

        self.assertEqual(result["session_type"], "Q")
        self.assertEqual(result["driver_code1"], "VER")
        self.assertEqual(result["driver_code2"], "NOR")


class WrapperTests(unittest.TestCase):
    def setUp(self) -> None:
        self._mcp_backup = sys.modules.get("mcp")
        self._mcp_server_backup = sys.modules.get("mcp.server")
        self._mcp_fastmcp_backup = sys.modules.get("mcp.server.fastmcp")

        fastmcp_module = types.ModuleType("mcp.server.fastmcp")

        class FastMCP:
            def __init__(self, _name: str) -> None:
                self.name = _name

            def tool(self):
                def decorator(fn):
                    return fn

                return decorator

        fastmcp_module.FastMCP = FastMCP
        sys.modules["mcp"] = types.ModuleType("mcp")
        sys.modules["mcp.server"] = types.ModuleType("mcp.server")
        sys.modules["mcp.server.fastmcp"] = fastmcp_module
        sys.modules.pop("f1_mcp_server", None)
        self.server = importlib.import_module("f1_mcp_server")

    def tearDown(self) -> None:
        for name, backup in (
            ("mcp", self._mcp_backup),
            ("mcp.server", self._mcp_server_backup),
            ("mcp.server.fastmcp", self._mcp_fastmcp_backup),
        ):
            if backup is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = backup

    def test_wrappers_forward_session_type(self) -> None:
        with patch.object(self.server, "_get_f1_results_impl", return_value={"ok": True}) as get_results:
            self.server.get_f1_results(2025, "Monza", session_type="Q")
        get_results.assert_called_once_with(2025, "Monza", session_type="Q")

        with patch.object(self.server, "_get_driver_lap_times_impl", return_value={"ok": True}) as get_laps:
            self.server.get_driver_lap_times(2025, "Bahrain", "VER", session_type="FP2")
        get_laps.assert_called_once_with(2025, "Bahrain", "VER", session_type="FP2")

        with patch.object(self.server, "_compare_driver_lap_times_impl", return_value={"ok": True}) as compare_laps:
            self.server.compare_driver_lap_times(2025, "Monza", "NOR", "LEC", session_type="Q")
        compare_laps.assert_called_once_with(2025, "Monza", "NOR", "LEC", session_type="Q")

        with patch.object(self.server, "_analyze_qualifying_runs_impl", return_value={"ok": True}) as analyze_runs:
            self.server.analyze_qualifying_runs(2025, "Monza", "NOR", session_type="Q")
        analyze_runs.assert_called_once_with(2025, "Monza", "NOR", session_type="Q")

        with patch.object(self.server, "_compare_qualifying_runs_impl", return_value={"ok": True}) as compare_runs:
            self.server.compare_qualifying_runs(2025, "Monza", "NOR", "LEC", session_type="Q")
        compare_runs.assert_called_once_with(2025, "Monza", "NOR", "LEC", session_type="Q")


if __name__ == "__main__":
    unittest.main()
