from urllib.request import urlopen
import json, fastf1
import pandas as pd
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


x = amount_of_races("Bahrain")
print(x[1])
