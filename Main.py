from urllib.request import urlopen
import json, fastf1
import pandas as pd
import numpy as np
import os

try:
    os.makedirs('cache', exist_ok=True)
except Exception as e:
    print(f"Cache already made")
fastf1.Cache.enable_cache('cache')

years = range(2021,2027)

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
    print(f"Total  {gp_name}  Grand Prixs found: {total_count}")
    return(total_count, years_array)

def load_race_results(gp_name, years_array):
    results_by_year = {}
    for year in years_array:
        try:
            session = fastf1.get_session(year, gp_name, 'R')
            session.load()
            results_by_year[year] = session.results
        except Exception as e:
            print(f"Error could not fetch race data for {gp_name} for year {year}")
    return results_by_year

def team_historical_performance(team, year, results_by_year):
    positions = []
    for past_year, results in results_by_year.items():
        if past_year >= year:
            continue
        team_rows = results[results['TeamName'].str.contains(team, case=False, na=False)]
        positions.extend(pd.to_numeric(team_rows['Position'], errors='coerce').dropna().tolist())
    average_pos = np.mean(positions) if positions else None
    team_races = len(positions)
    return average_pos, team_races

def driver_historical_performance(driver, year, result_by_year):
    positions = []
    for past_year, results in result_by_year.items():
        if past_year > year:
            continue
        driver_row = results[results['Abbreviation'].str.contains(driver, case=False, na=False)]
        positions.extend(pd.to_numeric(driver_row['Position'], errors='coerce').dropna().tolist())
    average_driver_pos = np.mean(positions) if positions else None
    driver_races = len(positions)
    return average_driver_pos, driver_races




schedule = fastf1.get_event_schedule(2025)
for i in schedule['Country']:
    print(i)
'''
rby = load_race_results("Bahrain", amount_of_races("bahrain")[1])
ap, tr =team_historical_performance("Red Bull Racing", 2025, rby)
print(ap, tr)
ap, tr =driver_historical_performance("VER", 2025, rby)
print(ap, tr)
'''