from urllib.request import urlopen
import json
import fastf1
import pandas as pd

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

def race_data(name):
    counts = amount_of_races(name)
    for year in years:
        try:    
            session = fastf1.get_session(year, name, 'Race') 
        except Exception as e:
            print(f"Could not fetch data for {year}: {e}")


   