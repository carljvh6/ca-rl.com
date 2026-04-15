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

    def test_analyze_driver_stints_rejects_qualifying(self) -> None:
        analysis_tools = importlib.import_module("f1_mcp.tools.analysis_tools")
        result = analysis_tools.analyze_driver_stints(2025, "Bahrain", "VER", session_type="Q")
        self.assertEqual(
            result["error"],
            "Stint analysis is only supported for race-like sessions (R, S).",
        )

    def test_compare_driver_stints_happy_path(self) -> None:
        analysis_tools = importlib.import_module("f1_mcp.tools.analysis_tools")
        stint_payload = {
            "session_type": "R",
            "driver_code": "VER",
            "stints": [
                {
                    "stint_number": 1,
                    "compound": "SOFT",
                    "start_lap": 1,
                    "end_lap": 10,
                    "num_laps": 10,
                    "laps": [],
                    "avg_lap_seconds_all": 91.0,
                    "avg_lap_seconds_clean": 90.5,
                    "median_lap_seconds_clean": 90.4,
                    "best_lap_seconds": 89.9,
                    "pace_trend_raw_seconds_per_lap": 0.08,
                    "pace_trend_robust_seconds_per_lap": 0.07,
                    "degradation_slope_seconds_per_lap": 0.08,
                    "clean_lap_count": 8,
                    "excluded_lap_count": 2,
                    "confidence": "high",
                    "confidence_reasons": ["8 clean laps"],
                    "late_stint_delta_seconds": 0.3,
                    "includes_out_lap": True,
                    "includes_in_lap": True,
                }
            ],
            "summary": {},
        }

        with patch.object(analysis_tools, "analyze_driver_stints", side_effect=[stint_payload, {**stint_payload, "driver_code": "NOR"}]):
            result = analysis_tools.compare_driver_stints(2025, "Miami", "VER", "NOR", session_type="R")

        self.assertEqual(result["session_type"], "R")
        self.assertEqual(result["driver_code1"], "VER")
        self.assertEqual(result["driver_code2"], "NOR")
        self.assertEqual(len(result["comparison"]["stint_matchups"]), 1)


class StintAnalysisTests(unittest.TestCase):
    def test_analyze_stints_marks_clean_metrics_and_summary(self) -> None:
        import pandas as pd

        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        laps = pd.DataFrame(
            [
                {"LapNumber": 1, "LapTime": pd.to_timedelta("0 days 00:01:35"), "LapTimeSeconds": 95.0, "Compound": "SOFT", "PitOutTime": pd.to_timedelta("0 days 00:00:01"), "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 2, "LapTime": pd.to_timedelta("0 days 00:01:31"), "LapTimeSeconds": 91.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 3, "LapTime": pd.to_timedelta("0 days 00:01:32"), "LapTimeSeconds": 92.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.to_timedelta("0 days 00:04:40"), "TrackStatus": "1"},
                {"LapNumber": 4, "LapTime": pd.to_timedelta("0 days 00:01:37"), "LapTimeSeconds": 97.0, "Compound": "MEDIUM", "PitOutTime": pd.to_timedelta("0 days 00:05:01"), "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 5, "LapTime": pd.to_timedelta("0 days 00:01:30"), "LapTimeSeconds": 90.0, "Compound": "MEDIUM", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
            ]
        )

        result = stint_analysis.analyze_stints(laps)
        self.assertEqual(result["summary"]["num_stints"], 2)
        self.assertEqual(result["stints"][0]["includes_out_lap"], True)
        self.assertEqual(result["stints"][0]["includes_in_lap"], True)
        self.assertEqual(result["stints"][0]["avg_lap_seconds_clean"], 91.0)
        self.assertEqual(result["summary"]["best_stint_by_avg_clean"]["stint_number"], 2)

    def test_infer_compound_uses_first_non_null_value(self) -> None:
        import pandas as pd

        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        stint_df = pd.DataFrame([{"Compound": None}, {"Compound": "soft"}, {"Compound": "SOFT"}])
        compound, source = stint_analysis.infer_stint_compound(stint_df)
        self.assertEqual(compound, "SOFT")
        self.assertEqual(source, "filled_from_stint")

    def test_infer_compound_all_null_returns_unknown(self) -> None:
        import pandas as pd

        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        stint_df = pd.DataFrame([{"Compound": None}, {"Compound": float("nan")}])
        compound, source = stint_analysis.infer_stint_compound(stint_df)
        self.assertEqual(compound, "UNKNOWN")
        self.assertEqual(source, "unknown")

    def test_pace_trend_sign_and_low_confidence_on_short_stint(self) -> None:
        import pandas as pd

        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        laps = pd.DataFrame(
            [
                {"LapNumber": 1, "LapTimeSeconds": 96.0, "Compound": "SOFT", "PitOutTime": pd.to_timedelta("0 days 00:00:01"), "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 2, "LapTimeSeconds": 90.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 3, "LapTimeSeconds": 91.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 4, "LapTimeSeconds": 93.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.to_timedelta("0 days 00:03:10"), "TrackStatus": "1"},
            ]
        )
        result = stint_analysis.analyze_stints(laps)
        stint = result["stints"][0]
        self.assertGreater(stint["pace_trend_robust_seconds_per_lap"], 0)
        self.assertEqual(stint["confidence"], "low")
        self.assertEqual(stint["clean_lap_count"], 2)

    def test_timedelta_to_float_seconds_conversion(self) -> None:
        import pandas as pd

        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        self.assertEqual(stint_analysis._to_float_seconds(pd.to_timedelta("0 days 00:01:31.500")), 91.5)
        self.assertEqual(stint_analysis._to_float_seconds("0 days 00:01:30"), 90.0)

    def test_late_stint_delta_known_sample(self) -> None:
        import pandas as pd

        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        laps = pd.DataFrame(
            [
                {"LapNumber": 1, "LapTimeSeconds": 95.0, "Compound": "SOFT", "PitOutTime": pd.to_timedelta("0 days 00:00:01"), "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 2, "LapTimeSeconds": 90.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 3, "LapTimeSeconds": 90.2, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 4, "LapTimeSeconds": 90.4, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 5, "LapTimeSeconds": 90.6, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 6, "LapTimeSeconds": 96.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.to_timedelta("0 days 00:05:40"), "TrackStatus": "1"},
            ]
        )
        result = stint_analysis.analyze_stints(laps)
        stint = result["stints"][0]
        self.assertAlmostEqual(stint["late_stint_delta_seconds"], 0.4, places=6)

    def test_trend_calculation_known_monotonic_sample(self) -> None:
        import pandas as pd

        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        laps = pd.DataFrame(
            [
                {"LapNumber": 1, "LapTimeSeconds": 96.0, "Compound": "SOFT", "PitOutTime": pd.to_timedelta("0 days 00:00:01"), "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 2, "LapTimeSeconds": 90.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 3, "LapTimeSeconds": 90.2, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 4, "LapTimeSeconds": 90.4, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 5, "LapTimeSeconds": 90.6, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.NaT, "TrackStatus": "1"},
                {"LapNumber": 6, "LapTimeSeconds": 97.0, "Compound": "SOFT", "PitOutTime": pd.NaT, "PitInTime": pd.to_timedelta("0 days 00:05:50"), "TrackStatus": "1"},
            ]
        )
        result = stint_analysis.analyze_stints(laps)
        stint = result["stints"][0]
        self.assertAlmostEqual(stint["pace_trend_raw_seconds_per_lap"], 0.2, places=6)
        self.assertAlmostEqual(stint["pace_trend_robust_seconds_per_lap"], 0.2, places=6)

    def test_compare_stints_marks_too_close_to_call(self) -> None:
        stint_analysis = importlib.import_module("f1_mcp.services.stint_analysis")
        driver1_stints = [
            {
                "stint_number": 1,
                "compound": "SOFT",
                "avg_lap_seconds_clean": 90.01,
                "median_lap_seconds_clean": 90.0,
                "best_lap_seconds": 89.8,
                "pace_trend_robust_seconds_per_lap": 0.02,
                "confidence": "medium",
                "confidence_reasons": ["5 clean laps"],
            }
        ]
        driver2_stints = [
            {
                "stint_number": 1,
                "compound": "SOFT",
                "avg_lap_seconds_clean": 90.04,
                "median_lap_seconds_clean": 90.02,
                "best_lap_seconds": 89.81,
                "pace_trend_robust_seconds_per_lap": 0.03,
                "confidence": "low",
                "confidence_reasons": ["4 clean laps"],
            }
        ]
        comparison = stint_analysis.compare_stints(driver1_stints, driver2_stints, driver1_code="VER", driver2_code="NOR")
        matchup = comparison["stint_matchups"][0]
        self.assertTrue(matchup["too_close_to_call"])
        self.assertEqual(matchup["faster_driver"], "Too close to call")

    def test_stint_prompt_discourages_speculative_narrative(self) -> None:
        markdown_backup = sys.modules.get("markdown")
        markdown_stub = types.ModuleType("markdown")
        markdown_stub.markdown = lambda text, extensions=None: text
        sys.modules["markdown"] = markdown_stub
        sys.modules.pop("f1_mcp.rendering.html_sections", None)
        html_sections = importlib.import_module("f1_mcp.rendering.html_sections")
        prompt = html_sections.build_stint_comparison_analysis_prompt(
            2025,
            "Bahrain",
            "VER",
            "NOR",
            {"session_type": "R", "comparison": {"stint_matchups": []}},
            "Compare the stints of Verstappen and Norris in Bahrain 2025",
        )
        self.assertIn("Do not overinterpret 2-3 clean laps.", prompt)
        self.assertIn("Never infer team or driver intent from short stints alone.", prompt)
        self.assertIn('Only claim "better tyre management"', prompt)
        if markdown_backup is None:
            sys.modules.pop("markdown", None)
        else:
            sys.modules["markdown"] = markdown_backup

    def test_rendering_formats_trend_and_delta_as_signed_seconds(self) -> None:
        markdown_backup = sys.modules.get("markdown")
        markdown_stub = types.ModuleType("markdown")
        markdown_stub.markdown = lambda text, extensions=None: text
        sys.modules["markdown"] = markdown_stub
        sys.modules.pop("f1_mcp.rendering.html_sections", None)
        html_sections = importlib.import_module("f1_mcp.rendering.html_sections")
        html = html_sections.render_single_driver_stint_table(
            [
                {
                    "stint_number": 1,
                    "compound": "SOFT",
                    "start_lap": 1,
                    "end_lap": 10,
                    "num_laps": 10,
                    "clean_lap_count": 8,
                    "confidence": "high",
                    "avg_lap_seconds_all": 91.0,
                    "avg_lap_seconds_clean": 90.5,
                    "best_lap_seconds": 89.9,
                    "pace_trend_robust_seconds_per_lap": -0.184,
                    "late_stint_delta_seconds": 0.312,
                    "includes_out_lap": True,
                    "includes_in_lap": True,
                }
            ]
        )
        self.assertIn("-0.184s/lap", html)
        self.assertIn("+0.312s", html)
        self.assertNotIn("-1:39.321", html)
        if markdown_backup is None:
            sys.modules.pop("markdown", None)
        else:
            sys.modules["markdown"] = markdown_backup


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

        with patch.object(self.server, "_analyze_driver_stints_impl", return_value={"ok": True}) as analyze_stints:
            self.server.analyze_driver_stints(2025, "Monza", "NOR", session_type="R")
        analyze_stints.assert_called_once_with(2025, "Monza", "NOR", session_type="R")

        with patch.object(self.server, "_compare_driver_stints_impl", return_value={"ok": True}) as compare_stints:
            self.server.compare_driver_stints(2025, "Monza", "NOR", "LEC", session_type="R")
        compare_stints.assert_called_once_with(2025, "Monza", "NOR", "LEC", session_type="R")


if __name__ == "__main__":
    unittest.main()
