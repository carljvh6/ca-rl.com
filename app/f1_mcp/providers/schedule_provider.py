"""Schedule dataframe access helpers."""

from __future__ import annotations

import pandas as pd
import fastf1


def get_schedule_df(year: int) -> pd.DataFrame:
    """Return the raw FastF1 schedule dataframe for a season."""
    schedule = fastf1.get_event_schedule(year)
    if schedule is None:
        return pd.DataFrame()
    return schedule.copy()

