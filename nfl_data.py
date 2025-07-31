# nfl_data.py

# Import packages
import pandas as pd
import numpy as np
import datetime as dt
from dateutil.relativedelta import relativedelta
import matplotlib.pyplot as plt
import nfl_data_py as nfl
import os
import IPython.display as ipd

# Clear all variables in the workspace
os.system('reset 2>/dev/null')

# Set display options for pandas
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)

# User created functions
def whatisthis(input_data):
    """
    This function prints a message indicating that it is a placeholder for future functionality.
    """

    ipd.display(ipd.HTML("<h3>Data Preview:</h3>"))
    ipd.display(input_data.head())
    ipd.display(ipd.HTML("<h3>Data Summary:</h3>"))
    ipd.display(input_data.describe())
    ipd.display(ipd.HTML("<h3>Data Information:</h3>"))
    ipd.display(input_data.info())

def get_class(obj):
    """
    Returns the class of an object.
    
    Parameters:
    obj: The object whose class is to be determined.
    
    Returns:
    The class of the object.
    """
    return print(obj.__class__.__name__)

################################################################################################################################

# Import NFL data
seasonal_data = nfl.import_seasonal_data(years = range(2020, 2025))
players_data = nfl.import_players().rename(columns={'gsis_id': 'player_id'})

# Merge dataframes
seasonal_data_enriched = pd.merge(seasonal_data, players_data, on='player_id', how='left', suffixes=('_seasonal', '_players'))

# Filter for specific positions
positions = [
    'QB', 
    'RB', 
    'WR', 
    'TE'
]
seasonal_data_enriched = seasonal_data_enriched[seasonal_data_enriched['position'].isin(positions)].reset_index(drop=True)
seasonal_data_enriched = seasonal_data_enriched[seasonal_data_enriched['season_type'] == 'REG'].reset_index(drop=True)
seasonal_data_enriched['birth_date'] = pd.to_datetime(seasonal_data_enriched['birth_date'])
seasonal_data_enriched['season_start_date'] = pd.to_datetime(seasonal_data_enriched['season'].astype(str) + '-08-01')
seasonal_data_enriched['age'] = seasonal_data_enriched.apply(
    lambda row: relativedelta(row['season_start_date'], row['birth_date']).years, 
    axis=1
)

# Define scoring array for fantasy football
# This dictionary contains the scoring rules for various player statistics in fantasy football.
# Each key represents a statistic, and the value represents the points awarded for that statistic.
scoring_array = {
    'passing_yards': .04,
    'passing_tds': 4,
    'interceptions': -2,
    'sacks': -1,
    'fumbles_lost': -2,
    '2pt_conversions': 2,
    'rushing_yards': .1,
    'rushing_tds': 6,
    'receptions': .5,
    'receiving_yards': .1,
    'receiving_tds': 6
}

# Format nfl_data_py data for scoring usage
# The following code formats the seasonal data to prepare it for fantasy scoring calculations.
fantasy_points_seasonal = pd.DataFrame(seasonal_data_enriched[['player_id', 'display_name', 'position', 'season', 'age', 'birth_date', 'team_abbr', 'height', 'weight']])
fantasy_points_seasonal['passing_yards'] = seasonal_data_enriched['passing_yards']
fantasy_points_seasonal['passing_tds'] = seasonal_data_enriched['passing_tds']
fantasy_points_seasonal['interceptions'] = seasonal_data_enriched['interceptions']
fantasy_points_seasonal['sacks'] = seasonal_data_enriched['sacks']
fantasy_points_seasonal['fumbles_lost'] = seasonal_data_enriched['sack_fumbles_lost'] + seasonal_data_enriched['rushing_fumbles_lost'] + seasonal_data_enriched['receiving_fumbles_lost']
fantasy_points_seasonal['2pt_conversions'] = seasonal_data_enriched['passing_2pt_conversions'] + seasonal_data_enriched['rushing_2pt_conversions'] + seasonal_data_enriched['receiving_2pt_conversions']
fantasy_points_seasonal['rushing_yards'] = seasonal_data_enriched['rushing_yards']
fantasy_points_seasonal['rushing_tds'] = seasonal_data_enriched['rushing_tds']
fantasy_points_seasonal['receptions'] = seasonal_data_enriched['receptions']
fantasy_points_seasonal['receiving_yards'] = seasonal_data_enriched['receiving_yards']
fantasy_points_seasonal['receiving_tds'] = seasonal_data_enriched['receiving_tds']

# Calculate fantasy points
fantasy_points_seasonal['fantasy_points'] = (
    fantasy_points_seasonal['passing_yards'] * scoring_array['passing_yards'] +
    fantasy_points_seasonal['passing_tds'] * scoring_array['passing_tds'] +
    fantasy_points_seasonal['interceptions'] * scoring_array['interceptions'] +
    fantasy_points_seasonal['sacks'] * scoring_array['sacks'] +
    fantasy_points_seasonal['fumbles_lost'] * scoring_array['fumbles_lost'] +
    fantasy_points_seasonal['2pt_conversions'] * scoring_array['2pt_conversions'] +
    fantasy_points_seasonal['rushing_yards'] * scoring_array['rushing_yards'] +
    fantasy_points_seasonal['rushing_tds'] * scoring_array['rushing_tds'] +
    fantasy_points_seasonal['receptions'] * scoring_array['receptions'] +
    fantasy_points_seasonal['receiving_yards'] * scoring_array['receiving_yards'] +
    fantasy_points_seasonal['receiving_tds'] * scoring_array['receiving_tds']
)

ipd.display(ipd.HTML("<h3>Fantasy Points Data Preview:</h3>"))
ipd.display(fantasy_points_seasonal.head())