import logging
from mcp.server.fastmcp import FastMCP
import fastf1
import pandas as pd
import plotly.express as px

mcp = FastMCP("f1_server")

@mcp.tool()
def get_f1_results(year: int, race: str) -> dict:
    """
    Get F1 race results for a given year and race.
    
    Args:
        year: The season year (e.g., 2024)
        race: The race name or search term (e.g., "Monaco", "Qatar Grand Prix")
    
    Returns:
        Dictionary with race results including driver names, teams, and positions
    """
    logging.info(f"Getting F1 results for {year} - {race}")
    try:
        session = fastf1.get_session(year, race, 'R')
        session.load()
        
        if not hasattr(session, "results") or session.results is None or session.results.empty:
            return {"error": f"No race data available for {year} - {race}"}
        
        cls = ['BroadcastName', 'TeamName', 'Position']
        df = session.results[cls].sort_values(by='Position', ascending=True)
        
        # Convert DataFrame to list of dicts for JSON serialization
        results = df.to_dict('records')
        return {
            "year": year,
            "race": race,
            "results": results
        }
    except Exception as e:
        logging.error(f"Error getting F1 results: {e}")
        return {"error": str(e)}


@mcp.tool()
def get_f1_schedule(year: int) -> dict:
    """
    Get the F1 schedule for a given year.
    
    Args:
        year: The season year (e.g., 2024)
    
    Returns:
        Dictionary with the race schedule including race names, dates, and locations
    """
    logging.info(f"Getting F1 schedule for {year}")
    try:
        schedule = fastf1.get_event_schedule(year)
        
        if schedule is None or schedule.empty:
            return {"error": f"No schedule data available for {year}"}
        
        # Select key columns
        cols = ['RoundNumber', 'EventName', 'Country', 'Location', 'EventDate']
        schedule_df = schedule[cols].copy()
        
        # Convert dates to strings for JSON serialization
        if 'EventDate' in schedule_df.columns:
            schedule_df['EventDate'] = schedule_df['EventDate'].astype(str)
        
        # Convert DataFrame to list of dicts
        schedule_list = schedule_df.to_dict('records')
        
        return {
            "year": year,
            "schedule": schedule_list
        }
    except Exception as e:
        logging.error(f"Error getting F1 schedule: {e}")
        return {"error": str(e)}


@mcp.tool()
def plot_driver_lap_times(year: int, race: str, driver_code: str) -> dict:
    """
    Plot lap times for a given driver in a particular race and year.
    
    Args:
        year: The season year (e.g., 2024)
        race: The race name or search term (e.g., "Monaco", "Qatar Grand Prix")
        driver_code: The driver code (e.g., "VER" for Verstappen, "NOR" for Norris)
    
    Returns:
        Dictionary with plot HTML and metadata
    """
    logging.info(f"Plotting lap times for {driver_code} in {year} - {race}")
    try:
        session = fastf1.get_session(year, race, 'R')
        session.load()
        
        laps_cls = ["Driver", "LapNumber", "LapTime", "Compound"]
        driver_laps = session.laps[session.laps.Driver == driver_code][laps_cls].copy()
        
        if driver_laps.empty:
            return {"error": f"No lap data found for driver {driver_code} in {year} - {race}"}
        
        # Ensure LapNumber is integer
        driver_laps["LapNumber"] = driver_laps["LapNumber"].astype(int)
        
        # Convert LapTime (timedelta) to total seconds for plotting
        driver_laps["LapTimeSeconds"] = driver_laps["LapTime"].dt.total_seconds()
        
        fig = px.line(
            driver_laps,
            x='LapNumber',
            y='LapTimeSeconds',
            title=f"{driver_code} Lap Times ({year} {race})",
            markers=True,
            color_discrete_sequence=["#24e2c2"]
        )
        fig.update_layout(
            template="plotly_dark",
            yaxis=dict(title='Lap Time (s)'),
            xaxis=dict(title='Lap Number', showgrid=False),
            plot_bgcolor="#181818",
            paper_bgcolor="#181818",
            font=dict(color="#f1f1f1"),
            title_font=dict(size=28, color="#f1f1f1"),
            margin=dict(l=50, r=30, t=80, b=50)
        )
        fig.update_traces(line=dict(width=3), marker=dict(size=7, color="#ff3b3f"))
        
        # Convert plot to JSON and create embeddable HTML
        plot_id = f"plot_{driver_code}_{year}_{race.replace(' ', '_').replace('-', '_')}"
        plot_json = fig.to_json()
        
        # Create embeddable HTML with Plotly CDN
        # Load Plotly dynamically if not already loaded, then render plot
        plot_html = f"""<div id="{plot_id}" style="width:100%;height:600px;"></div>
<script>
(function() {{
    var plotData = {plot_json};
    function renderPlot() {{
        if (typeof Plotly !== 'undefined') {{
            Plotly.newPlot('{plot_id}', plotData.data, plotData.layout, {{responsive: true}});
        }} else {{
            var script = document.createElement('script');
            script.src = 'https://cdn.plot.ly/plotly-2.26.0.min.js';
            script.onload = function() {{
                Plotly.newPlot('{plot_id}', plotData.data, plotData.layout, {{responsive: true}});
            }};
            document.head.appendChild(script);
        }}
    }}
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', renderPlot);
    }} else {{
        renderPlot();
    }}
}})();
</script>"""
        
        return {
            "year": year,
            "race": race,
            "driver_code": driver_code,
            "plot_html": plot_html
        }
    except Exception as e:
        logging.error(f"Error plotting lap times: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
