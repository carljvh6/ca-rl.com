import logging
from mcp.server.fastmcp import FastMCP
import fastf1
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import base64
from io import BytesIO

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
        
        # Filter out rows with invalid (NaT) lap times
        driver_laps = driver_laps[pd.notna(driver_laps["LapTime"])].copy()
        
        if driver_laps.empty:
            return {"error": f"No valid lap time data found for driver {driver_code} in {year} - {race}"}
        
        # Ensure LapNumber is integer
        driver_laps["LapNumber"] = driver_laps["LapNumber"].astype(int)
        
        # Convert LapTime (timedelta) to total seconds for plotting
        driver_laps["LapTimeSeconds"] = driver_laps["LapTime"].dt.total_seconds()
        
        # Ensure LapTimeSeconds is numeric and remove any remaining NaN values
        driver_laps["LapTimeSeconds"] = pd.to_numeric(driver_laps["LapTimeSeconds"], errors='coerce')
        driver_laps = driver_laps[pd.notna(driver_laps["LapTimeSeconds"])].copy()
        
        if driver_laps.empty:
            return {"error": f"No valid lap time data found for driver {driver_code} in {year} - {race}"}
        
        # Sort by lap number and reset index to ensure proper ordering
        driver_laps = driver_laps.sort_values("LapNumber").reset_index(drop=True)
        
        # Convert to native Python types
        lap_numbers = driver_laps["LapNumber"].astype(int).tolist()
        lap_times_seconds = driver_laps["LapTimeSeconds"].astype(float).tolist()
        
        # Create matplotlib figure with dark theme
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 6), facecolor='#181818')
        ax.set_facecolor('#181818')
        
        # Plot the data
        ax.plot(lap_numbers, lap_times_seconds, marker='o', linewidth=3, 
                markersize=7, color='#ff3b3f', markerfacecolor='#ff3b3f', 
                markeredgecolor='#ff3b3f')
        
        # Set labels and title
        ax.set_xlabel('Lap Number', color='#f1f1f1', fontsize=14)
        ax.set_ylabel('Lap Time (s)', color='#f1f1f1', fontsize=14)
        ax.set_title(f"{driver_code} Lap Times ({year} {race})", 
                     color='#f1f1f1', fontsize=20, fontweight='bold', pad=20)
        
        # Calculate reasonable y-axis range
        min_time = min(lap_times_seconds)
        max_time = max(lap_times_seconds)
        time_range = max_time - min_time
        y_min = max(0, min_time - time_range * 0.1)
        y_max = max_time + time_range * 0.1
        ax.set_ylim(y_min, y_max)
        
        # Style the axes
        ax.tick_params(colors='#f1f1f1', labelsize=12)
        ax.grid(True, alpha=0.3, color='#666666')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color('#666666')
        ax.spines['left'].set_color('#666666')
        
        # Adjust layout
        plt.tight_layout()
        
        # Convert to base64 encoded image
        img_buffer = BytesIO()
        fig.savefig(img_buffer, format='png', facecolor='#181818', 
                   edgecolor='none', dpi=100, bbox_inches='tight')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        plt.close(fig)
        
        # Create HTML with embedded image
        plot_html = f'<div style="width:100%; text-align:center;"><img src="data:image/png;base64,{img_base64}" style="max-width:100%; height:auto;" alt="Lap Times Plot" /></div>'
        
        # Convert lap data to list of dicts for table display
        lap_data = driver_laps[["LapNumber", "LapTime", "Compound"]].copy()
        # Convert LapTime to string format for display
        lap_data["LapTime"] = lap_data["LapTime"].astype(str)
        lap_records = lap_data.to_dict('records')
        
        return {
            "year": year,
            "race": race,
            "driver_code": driver_code,
            "plot_html": plot_html,
            "lap_data": lap_records
        }
    except Exception as e:
        logging.error(f"Error plotting lap times: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
