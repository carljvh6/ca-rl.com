import logging
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)
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
    logger.info(f"Getting F1 results for {year} - {race}")
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
        logger.error(f"Error getting F1 results: {e}")
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
    logger.info(f"Getting F1 schedule for {year}")
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
        logger.error(f"Error getting F1 schedule: {e}")
        return {"error": str(e)}


@mcp.tool()
def get_driver_lap_times(year: int, race: str, driver_code: str) -> dict:
    """
    Get lap times data for a given driver in a particular race and year.
    
    Args:
        year: The season year (e.g., 2024)
        race: The race name or search term (e.g., "Monaco", "Qatar Grand Prix")
        driver_code: The driver code (e.g., "VER" for Verstappen, "NOR" for Norris)
    
    Returns:
        Dictionary with lap times data including lap numbers, lap times, and tire compounds
    """
    logger.info(f"Getting lap times for {driver_code} in {year} - {race}")
    try:
        session = fastf1.get_session(year, race, 'R')
        session.load()
        
        # Include pit stop times in the columns
        laps_cls = ["Driver", "LapNumber", "LapTime", "Compound", "PitInTime", "PitOutTime"]
        driver_laps = session.laps[session.laps.Driver == driver_code][laps_cls].copy()
        
        if driver_laps.empty:
            return {"error": f"No lap data found for driver {driver_code} in {year} - {race}"}
        
        # Filter out rows with invalid (NaT) lap times
        driver_laps = driver_laps[pd.notna(driver_laps["LapTime"])].copy()
        
        if driver_laps.empty:
            return {"error": f"No valid lap time data found for driver {driver_code} in {year} - {race}"}
        
        # Ensure LapNumber is integer
        driver_laps["LapNumber"] = driver_laps["LapNumber"].astype(int)
        
        # Convert LapTime (timedelta) to total seconds for easier use
        driver_laps["LapTimeSeconds"] = driver_laps["LapTime"].dt.total_seconds()
        
        # Ensure LapTimeSeconds is numeric and remove any remaining NaN values
        driver_laps["LapTimeSeconds"] = pd.to_numeric(driver_laps["LapTimeSeconds"], errors='coerce')
        driver_laps = driver_laps[pd.notna(driver_laps["LapTimeSeconds"])].copy()
        
        if driver_laps.empty:
            return {"error": f"No valid lap time data found for driver {driver_code} in {year} - {race}"}
        
        # Sort by lap number and reset index to ensure proper ordering
        driver_laps = driver_laps.sort_values("LapNumber").reset_index(drop=True)
        
        # Convert lap data to list of dicts
        lap_data = driver_laps[["LapNumber", "LapTime", "LapTimeSeconds", "Compound", "PitInTime", "PitOutTime"]].copy()
        # Convert LapTime to string format for display
        lap_data["LapTime"] = lap_data["LapTime"].astype(str)
        # Convert PitInTime and PitOutTime to string format (they may be NaT)
        lap_data["PitInTime"] = lap_data["PitInTime"].astype(str)
        lap_data["PitOutTime"] = lap_data["PitOutTime"].astype(str)
        lap_records = lap_data.to_dict('records')
        
        return {
            "year": year,
            "race": race,
            "driver_code": driver_code,
            "lap_data": lap_records
        }
    except Exception as e:
        logger.error(f"Error getting lap times: {e}")
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
    logger.info(f"Plotting lap times for {driver_code} in {year} - {race}")
    try:
        # Get lap times data using the separate function
        lap_times_result = get_driver_lap_times(year, race, driver_code)
        
        if "error" in lap_times_result:
            return lap_times_result
        
        lap_data = lap_times_result["lap_data"]
        
        if not lap_data:
            return {"error": f"No lap data available for plotting driver {driver_code} in {year} - {race}"}
        
        # Extract lap numbers and lap times in seconds for plotting
        lap_numbers = [lap["LapNumber"] for lap in lap_data]
        lap_times_seconds = [lap["LapTimeSeconds"] for lap in lap_data]
        
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
        
        return {
            "year": year,
            "race": race,
            "driver_code": driver_code,
            "plot_html": plot_html,
            "lap_data": lap_data
        }
    except Exception as e:
        logger.error(f"Error plotting lap times: {e}")
        return {"error": str(e)}


@mcp.tool()
def compare_driver_lap_times(year: int, race: str, driver_code1: str, driver_code2: str) -> dict:
    """
    Compare lap times between two drivers in a particular race and year.
    Plots both drivers' lap times on the same graph.
    
    Args:
        year: The season year (e.g., 2024)
        race: The race name or search term (e.g., "Monaco", "Qatar Grand Prix")
        driver_code1: The first driver code (e.g., "HAM" for Hamilton)
        driver_code2: The second driver code (e.g., "VER" for Verstappen)
    
    Returns:
        Dictionary with comparison plot HTML and lap data for both drivers
    """
    logger.info(f"Comparing lap times for {driver_code1} vs {driver_code2} in {year} - {race}")
    try:
        # Get lap times for both drivers
        driver1_result = get_driver_lap_times(year, race, driver_code1)
        driver2_result = get_driver_lap_times(year, race, driver_code2)
        
        if "error" in driver1_result:
            return {"error": f"Error getting data for {driver_code1}: {driver1_result['error']}"}
        if "error" in driver2_result:
            return {"error": f"Error getting data for {driver_code2}: {driver2_result['error']}"}
        
        driver1_data = driver1_result["lap_data"]
        driver2_data = driver2_result["lap_data"]
        
        if not driver1_data:
            return {"error": f"No lap data available for driver {driver_code1} in {year} - {race}"}
        if not driver2_data:
            return {"error": f"No lap data available for driver {driver_code2} in {year} - {race}"}
        
        # Extract lap numbers and lap times in seconds for plotting
        driver1_laps = [lap["LapNumber"] for lap in driver1_data]
        driver1_times = [lap["LapTimeSeconds"] for lap in driver1_data]
        driver2_laps = [lap["LapNumber"] for lap in driver2_data]
        driver2_times = [lap["LapTimeSeconds"] for lap in driver2_data]
        
        # Extract pit stop information
        def get_pit_stop_laps(lap_data):
            pit_laps = []
            for lap in lap_data:
                pit_in = lap.get("PitInTime", "")
                pit_out = lap.get("PitOutTime", "")
                # Check if pit stop occurred
                if (pit_in and pit_in != "NaT" and pit_in != "nat" and str(pit_in) != "nan") or \
                   (pit_out and pit_out != "NaT" and pit_out != "nat" and str(pit_out) != "nan"):
                    pit_laps.append(lap.get("LapNumber"))
            return pit_laps
        
        driver1_pit_laps = get_pit_stop_laps(driver1_data)
        driver2_pit_laps = get_pit_stop_laps(driver2_data)
        
        # Create matplotlib figure with dark theme
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(14, 7), facecolor='#181818')
        ax.set_facecolor('#181818')
        
        # Plot both drivers
        ax.plot(driver1_laps, driver1_times, marker='o', linewidth=3, 
                markersize=6, color='#ff3b3f', markerfacecolor='#ff3b3f', 
                markeredgecolor='#ff3b3f', label=driver_code1, alpha=0.9)
        ax.plot(driver2_laps, driver2_times, marker='s', linewidth=3, 
                markersize=6, color='#3b82f6', markerfacecolor='#3b82f6', 
                markeredgecolor='#3b82f6', label=driver_code2, alpha=0.9)
        
        # Mark pit stops with vertical lines
        for pit_lap in driver1_pit_laps:
            ax.axvline(x=pit_lap, color='#ff3b3f', linestyle='--', alpha=0.5, linewidth=2)
        for pit_lap in driver2_pit_laps:
            ax.axvline(x=pit_lap, color='#3b82f6', linestyle='--', alpha=0.5, linewidth=2)
        
        # Set labels and title
        ax.set_xlabel('Lap Number', color='#f1f1f1', fontsize=14)
        ax.set_ylabel('Lap Time (s)', color='#f1f1f1', fontsize=14)
        ax.set_title(f"{driver_code1} vs {driver_code2} Lap Times Comparison ({year} {race})", 
                     color='#f1f1f1', fontsize=20, fontweight='bold', pad=20)
        
        # Calculate reasonable y-axis range (considering both drivers)
        all_times = driver1_times + driver2_times
        min_time = min(all_times)
        max_time = max(all_times)
        time_range = max_time - min_time
        y_min = max(0, min_time - time_range * 0.1)
        y_max = max_time + time_range * 0.1
        ax.set_ylim(y_min, y_max)
        
        # Add legend with pit stop indicators
        legend_elements = [
            plt.Line2D([0], [0], color='#ff3b3f', marker='o', linestyle='-', linewidth=3, markersize=6, label=driver_code1),
            plt.Line2D([0], [0], color='#3b82f6', marker='s', linestyle='-', linewidth=3, markersize=6, label=driver_code2)
        ]
        if driver1_pit_laps or driver2_pit_laps:
            legend_elements.append(plt.Line2D([0], [0], color='gray', linestyle='--', linewidth=2, label='Pit Stops'))
        ax.legend(handles=legend_elements, loc='best', fontsize=12, framealpha=0.3)
        
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
        plot_html = f'<div style="width:100%; text-align:center;"><img src="data:image/png;base64,{img_base64}" style="max-width:100%; height:auto;" alt="Lap Times Comparison Plot" /></div>'
        
        return {
            "year": year,
            "race": race,
            "driver_code1": driver_code1,
            "driver_code2": driver_code2,
            "plot_html": plot_html,
            "driver1_lap_data": driver1_data,
            "driver2_lap_data": driver2_data
        }
    except Exception as e:
        logger.error(f"Error comparing lap times: {e}")
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run()
