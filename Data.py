import os
import time
from functools import lru_cache
import fastf1
import numpy as np
import pandas as pd
 
try:
    from fastf1.exceptions import RateLimitExceededError
except ImportError:
    from fastf1 import RateLimitExceededError
 
os.makedirs('cache', exist_ok=True)
fastf1.Cache.enable_cache('cache')
 
years = range(2021, 2027)
 
RESULTS_ONLY = dict(laps=False, telemetry=False, weather=False, messages=False)
LAPS_ONLY = dict(telemetry=False, weather=False, messages=False)
 
 
def load_session(year, event, code, **load_kwargs):
    while True:
        try:
            session = fastf1.get_session(year, event, code)
            session.load(**load_kwargs)
            return session
        except RateLimitExceededError:
            print("Rate limit hit - waiting 10 minutes before retrying (cache is kept)...")
            time.sleep(600)
 
 
def amount_of_races(gp_name):
    total_count = 0
    years_array = []
    for year in years:
        try:
            schedule = fastf1.get_event_schedule(year)
            matching_races = schedule[schedule['EventName'].str.contains(gp_name, case=False, na=False)]
            races_only = matching_races[matching_races['EventFormat'] != 'testing']
            for idx, race in races_only.iterrows():
                if pd.to_datetime(race['EventDate']).tz_localize(None) < pd.Timestamp.now():
                    total_count += 1
                    years_array.append(year)
        except Exception as e:
            print(f"Could not fetch data for {year}: {e}")
    print(f"Total {gp_name} Grand Prixs found: {total_count}")
    return total_count, years_array
 
 
def load_race_results(gp_name, years_array):
    results_by_year = {}
    for year in years_array:
        try:
            session = load_session(year, gp_name, 'R', **RESULTS_ONLY)
            results_by_year[year] = session.results
        except Exception as e:
            print(f"Error could not fetch race data for {gp_name} for year {year}: {e}")
    return results_by_year
 
 
def team_historical_performance(team, year, results_by_year):
    positions = []
    for past_year, results in results_by_year.items():
        if past_year >= year:
            continue
        team_rows = results[results['TeamName'].str.contains(team, case=False, na=False, regex=False)]
        positions.extend(pd.to_numeric(team_rows['Position'], errors='coerce').dropna().tolist())
    average_pos = np.mean(positions) if positions else None
    team_races = len(positions)
    return average_pos, team_races
 
 
def driver_historical_performance(driver, year, result_by_year):
    positions = []
    for past_year, results in result_by_year.items():
        if past_year >= year:
            continue
        driver_row = results[results['Abbreviation'].str.contains(driver, case=False, na=False, regex=False)]
        positions.extend(pd.to_numeric(driver_row['Position'], errors='coerce').dropna().tolist())
    average_driver_pos = np.mean(positions) if positions else None
    driver_races = len(positions)
    return average_driver_pos, driver_races
 
 
def power_proxy(gp_name, year):
    try:
        quali = load_session(year, gp_name, 'Q', **LAPS_ONLY)
        return quali.laps.groupby("Driver")['SpeedST'].max().to_dict()
    except Exception as e:
        print(f"Error no data could be found for power proxy ({gp_name} {year}): {e}")
        return {}
 
 
@lru_cache(maxsize=None)
def current_standings(year):
    schedule = fastf1.get_event_schedule(year)
    races_only = schedule[schedule['EventFormat'] != 'testing'].sort_values('RoundNumber')
 
    standings_before = {}
    running_totals = {}
 
    for _, race in races_only.iterrows():
        rnd = race['RoundNumber']
        standings_before[rnd] = dict(running_totals)
 
        if pd.to_datetime(race['EventDate']).tz_localize(None) >= pd.Timestamp.now():
            continue
 
        codes = ['R']
        if 'sprint' in str(race['EventFormat']).lower():
            codes.append('S')
 
        for code in codes:
            try:
                session = load_session(year, rnd, code, **RESULTS_ONLY)
                for _, row in session.results.iterrows():
                    points = row['Points'] if pd.notna(row['Points']) else 0
                    team = row['TeamName']
                    running_totals[team] = running_totals.get(team, 0) + points
            except Exception as e:
                print(f"Could not fetch {year} round {rnd} ({code}): {e}")
 
    return standings_before
 
 
def race_data(gp_name):
    years_array = sorted(set(amount_of_races(gp_name)[1]))
    results_by_year = load_race_results(gp_name, years_array)
 
    rows = []
    for year, results in results_by_year.items():
        try:
            event = fastf1.get_session(year, gp_name, 'R').event
        except Exception as e:
            print(f"Could not get event info for {gp_name} {year}: {e}")
            continue
 
        speed = power_proxy(gp_name, year)
        standings = current_standings(year).get(event['RoundNumber'], {})
 
        for _, row in results.iterrows():
            driver, team = row['Abbreviation'], row['TeamName']
            team_avg, team_races = team_historical_performance(team, year, results_by_year)
            driver_avg, driver_races = driver_historical_performance(driver, year, results_by_year)
            rows.append({
                'year': year, 'round': event['RoundNumber'], 'gp': gp_name,
                'location': event['Location'], 'driver': driver, 'team': team,
                'grid_position': row['GridPosition'], 'finish_position': row['Position'],
                'points': row['Points'],
                'team_avg_finish_at_gp': team_avg, 'team_races_at_gp': team_races,
                'driver_avg_finish_at_gp': driver_avg, 'driver_races_at_gp': driver_races,
                'team_points_before_race': standings.get(team),
                'speed_trap_max': speed.get(driver),
            })
 
    return pd.DataFrame(rows)
 
 
def build_dataset(gp_names):
    return pd.concat([race_data(gp) for gp in gp_names], ignore_index=True)
 
 
if __name__ == '__main__':
    schedule = fastf1.get_event_schedule(2025)
    gp_list = schedule[schedule['EventFormat'] != 'testing']['EventName'].tolist()
 
    df = build_dataset(gp_list)
    print(df)
    print(df[['team_points_before_race', 'speed_trap_max']].notna().mean())
    df.to_csv('full_training_data.csv', index=False)
