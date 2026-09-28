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

def power_proxy(gp_name, year):
    try:
        quali = fastf1.get_event_session(gp_name, year,'Q')
        quali.load()
        return quali.laps.groupby("Abbreviation")['SpeedST'].max().to_dict()
    except Exception as e:
        print(f"Error no data could be found for power proxy")

def current_standings(year):
    schedule = fastf1.get_event_schedule(year)
    races_only = schedule[schedule['EventFormat'] != 'Testing'].sort_values('RoundNumber')

    running_totals = {}
    

    for _, race in races_only.iterrows():
        rnd = race['RoundNumber']
        try:
            session = fastf1.get_session(year, rnd, 'Race')
            session.load()
            for _, row in session.results.iterrows():
                driver = row['Abbreviation']
                points = row['Points'] if pd.notna(row['Points']) else 0
                running_totals[driver] = running_totals.get(driver, 0) + points
        except Exception as e:
            print(f"Could not fetch {year} round {rnd}: {e}")
        

    return running_totals

def build_data():
    results_by_location = {}
    events = []
    for year in years:
        try:
            schedule = fastf1.get_event_schedule(year)
            races_only = schedule[schedule['EventFormat'] != 'testing'].sort_values('RoundNumber')
        except Exception as e:
            print(f"Could not fetch schedule for {year}: {e}")
            continue
        running_points = {}
        for _, event in races_only.iterrows():
            if pd.to_datetime(event['EventDate']).tz_localize(None) >= pd.Timestamp.now():
                continue
 
            try:
                session = fastf1.get_session(year, event['RoundNumber'], 'Race')
                session.load()
            except Exception as e:
                print(f"Could not fetch {year} round {event['RoundNumber']}: {e}")
                continue
 
            location = event['Location']
            results_by_location.setdefault(location, {})[year] = session.results
            events.append({
                'year': year,
                'round': event['RoundNumber'],
                'gp': event['EventName'],
                'location': location,
                'standings_before': dict(running_points),
            })
 
            for _, row in session.results.iterrows():
                points = row['Points'] if pd.notna(row['Points']) else 0
                running_points[row['TeamName']] = running_points.get(row['TeamName'], 0) + points
 
    all_rows = []
    for ev in events:
        year, rnd, gp_name, location = ev['year'], ev['round'], ev['gp'], ev['location']
        results = results_by_location[location][year]
 
        speed_by_driver = power_proxy_by_round(year, rnd)
        standings_before = ev['standings_before']
 
        for _, row in results.iterrows():
            driver = row['Abbreviation']
            team = row['TeamName']
            team_hist = team_historical_performance(team, year, results_by_location[location])
            all_rows.append({
                'year': year,
                'gp': gp_name,
                'location': location,
                'driver': driver,
                'team': team,
                'grid_position': row['GridPosition'],
                'finish_position': row['Position'],
                'team_avg_finish_at_gp': team_hist['team_avg_finish_at_gp'],
                'team_races_at_gp': team_hist['team_races_at_gp'],
                'team_points_before_race': standings_before.get(team, None),
                'speed_trap_max': speed_by_driver.get(driver, None),
            })
            
    return pd.DataFrame(all_rows)

print(build_data())
