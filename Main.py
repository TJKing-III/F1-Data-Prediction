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

def time_split(df, n_test_races=N_TEST_RACES):
    races = df[['year', 'round']].drop_duplicates().sort_values(['year', 'round'])
    test_index = races.tail(n_test_races).set_index(['year', 'round']).index
    is_test = df.set_index(['year', 'round']).index.isin(test_index)
    return df[~is_test], df[is_test]


def mean_spearman(frame, pred_col):
    scores = [
        spearmanr(g[pred_col], g['finish_position'])[0]
        for _, g in frame.groupby(['year', 'round'])
    ]
    return float(np.nanmean(scores))


def fit_and_score(train, test, features):
    model = make_model()
    model.fit(train[features], train['finish_position'])
    preds = model.predict(test[features])
    return model, preds, mean_absolute_error(test['finish_position'], preds)


def evaluate(df):
    train, test = time_split(df)
    print(f"Train rows: {len(train)} | Test rows: {len(test)} "
          f"({N_TEST_RACES} most recent races)\n")

    model, preds, mae = fit_and_score(train, test, FEATURES)
    test = test.assign(pred=preds)

    baseline_mae = mean_absolute_error(test['finish_position'], test['grid_position'])
    print(f"Model MAE:              {mae:.2f} positions")
    print(f"Baseline MAE (grid):    {baseline_mae:.2f} positions")
    print(f"Model Spearman:         {mean_spearman(test, 'pred'):.3f}")
    print(f"Baseline Spearman:      {mean_spearman(test, 'grid_position'):.3f}\n")
    no_power = [f for f in FEATURES if f != 'speed_trap_delta']
    _, _, mae_no_power = fit_and_score(train, test, no_power)
    print(f"MAE without speed_trap_delta: {mae_no_power:.2f}  |  with: {mae:.2f}\n")

    imp = permutation_importance(model, test[FEATURES], test['finish_position'],
                                 n_repeats=20, random_state=0,
                                 scoring='neg_mean_absolute_error')
    print("Permutation importance (higher = model relies on it more):")
    for name, val in sorted(zip(FEATURES, imp.importances_mean), key=lambda x: -x[1]):
        print(f"  {name:24s} {val:.3f}")
    print()

def next_event():
    now = pd.Timestamp.now()
    schedule = fastf1.get_event_schedule(now.year)
    schedule = schedule[schedule['EventFormat'] != 'testing']
    dates = pd.to_datetime(schedule['EventDate']).dt.tz_localize(None)
    return schedule[dates > now].iloc[0]


def build_upcoming_features(df, event):
    year = int(event['EventDate'].year)
    rnd = int(event['RoundNumber'])
    location = event['Location']

    quali = fastf1.get_session(year, rnd, 'Q')
    quali.load()
    q = quali.results[['Abbreviation', 'TeamName', 'Position']].copy()
    q['grid_position'] = pd.to_numeric(q['Position'], errors='coerce')

    speed = quali.laps.groupby('Driver')['SpeedST'].max()
    season_points = df[df['year'] == year].groupby('team')['points'].sum()

    rows = []
    for _, r in q.iterrows():
        team = r['TeamName']
        past = df[(df['location'] == location) & (df['year'] < year) & (df['team'] == team)]
        rows.append({
            'year': year,
            'round': rnd,
            'driver': r['Abbreviation'],
            'team': team,
            'grid_position': r['grid_position'],
            'team_avg_finish_at_gp': past['finish_position'].mean() if len(past) else np.nan,
            'team_races_at_gp': len(past),
            'team_points_before_race': season_points.get(team, 0.0),
            'speed_trap_max': speed.get(r['Abbreviation'], np.nan),
        })

    return add_relative_features(pd.DataFrame(rows))


def event_by_round(year, round_number):
    schedule = fastf1.get_event_schedule(year)
    return schedule[schedule['RoundNumber'] == round_number].iloc[0]


def backtest_race(df, year, round_number):
    event = event_by_round(year, round_number)
    print(f"Backtesting: {event['EventName']} {year} (round {round_number})\n")
    train_df = df[~((df['year'] == year) & (df['round'] == round_number))]

    upcoming = build_upcoming_features(train_df, event)

    model = make_model()
    model.fit(train_df[FEATURES], train_df['finish_position'])
    upcoming['predicted_score'] = model.predict(upcoming[FEATURES])
    upcoming['predicted_position'] = upcoming['predicted_score'].rank(method='first').astype(int)

    actual = df[(df['year'] == year) & (df['round'] == round_number)][['driver', 'finish_position']]
    compare = upcoming.merge(actual, on='driver', how='left')
    compare = compare.sort_values('predicted_position')

    mae = mean_absolute_error(compare['finish_position'].dropna(),
                               compare.loc[compare['finish_position'].notna(), 'predicted_position'])
    print(f"Backtest MAE: {mae:.2f} positions\n")
    return compare[['predicted_position', 'driver', 'team', 'grid_position',
                     'predicted_score', 'finish_position']]


def predict_next_race(df):
    event = next_event()
    print(f"Predicting: {event['EventName']} (round {event['RoundNumber']})\n")

    try:
        upcoming = build_upcoming_features(df, event)
    except Exception as e:
        print(f"Could not build features (has qualifying happened yet?): {e}")
        return None

    model = make_model()
    model.fit(df[FEATURES], df['finish_position'])

    upcoming['predicted_score'] = model.predict(upcoming[FEATURES])
    upcoming['predicted_position'] = upcoming['predicted_score'].rank(method='first').astype(int)
    return upcoming.sort_values('predicted_position')[
        ['predicted_position', 'driver', 'team', 'grid_position', 'predicted_score']
    ]


if __name__ == '__main__':
    data = load_data()
    evaluate(data)
    last_year, last_round = data.sort_values(['year', 'round'])[['year', 'round']].iloc[-1]
    result = backtest_race(data, int(last_year), int(last_round))
    print(result.to_string(index=False))

    print("\n---\n")

    next_result = predict_next_race(data)
    if next_result is not None:
        print(next_result.to_string(index=False))