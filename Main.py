import fastf1
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance
from sklearn.metrics import mean_absolute_error

 
fastf1.Cache.enable_cache('cache')
 
DATA_PATH = 'full_training_data.csv'
N_TEST_RACES = 5 

FEATURES = [
    'grid_position',
    'team_avg_finish_at_gp',
    'team_races_at_gp',
    'points_share',
    'speed_trap_delta',
]

def add_relative_features(df):
    df = df.copy()
    grp = df.groupby(['year', 'round'])
 
    max_points = grp['team_points_before_race'].transform('max')
    df['points_share'] = np.where(max_points > 0, df['team_points_before_race'] / max_points, 0.0)
 
    df['speed_trap_delta'] = df['speed_trap_max'] - grp['speed_trap_max'].transform('mean')
    return df

def load_data(path=DATA_PATH):
    df = pd.read_csv(path)
    df = df.dropna(subset=['finish_position', 'grid_position'])
    df['grid_position'] = df['grid_position'].replace(0, 20)
    return add_relative_features(df)

def make_model():
    return HistGradientBoostingRegressor(max_iter=200, max_depth=3, learning_rate=0.05, random_state=0)
