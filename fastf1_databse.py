import fastf1
import pandas as pd
import os
import time
from sqlalchemy import create_engine, inspect

# ============================================================
# 1. SETUP
# ============================================================

script_folder = os.path.dirname(os.path.abspath(__file__))

# FastF1 cache
cache_dir = os.path.join(script_folder, "fastf1_cache")
os.makedirs(cache_dir, exist_ok=True)
fastf1.Cache.enable_cache(cache_dir)

# SQLite database
database_path = os.path.join(script_folder, "f1_database.db")
engine = create_engine(f"sqlite:///{database_path}")

print("=" * 60)
print("F1 HISTORICAL DATA DOWNLOADER")
print("=" * 60)
print(f"Database: {database_path}")
print(f"Cache:    {cache_dir}")
print()


# ============================================================
# 2. DATABASE SETUP
# ============================================================

table_name = "historical_driver_summary"

inspector = inspect(engine)

if inspector.has_table(table_name):
    print(f"✓ Database table '{table_name}' already exists.")
    print("  Existing data will NOT be deleted.")
else:
    print(f"✓ Table '{table_name}' does not exist yet.")
    print("  It will be created after the first successful race.")

print()


# ============================================================
# 3. TRACK PROGRESS
# ============================================================

successful_races = 0
failed_races = 0
skipped_races = 0

# Keep a record of races already stored so we don't download them
# again if the script is restarted.
existing_races = set()

if inspector.has_table(table_name):
    try:
        existing_df = pd.read_sql(
            f"""
            SELECT DISTINCT Year, Race_Name
            FROM {table_name}
            """,
            engine
        )

        existing_races = set(
            zip(existing_df["Year"], existing_df["Race_Name"])
        )

        print(f"✓ Found {len(existing_races)} races already in database.")

    except Exception as e:
        print(f" Could not read existing database data: {e}")

print()


# ============================================================
# 4. DOWNLOAD YEARS
# ============================================================

for year in range(2021, 2027):

    print()
    print("=" * 60)
    print(f"YEAR: {year}")
    print("=" * 60)

    # --------------------------------------------------------
    # Get season schedule
    # --------------------------------------------------------

    schedule = None
    schedule_attempts = 0
    max_schedule_attempts = 3

    while schedule is None and schedule_attempts < max_schedule_attempts:

        schedule_attempts += 1

        try:
            print(
                f"Getting {year} schedule "
                f"(attempt {schedule_attempts}/{max_schedule_attempts})..."
            )

            schedule = fastf1.get_event_schedule(year)

            print(
                f"✓ Schedule loaded: "
                f"{len(schedule)} events found."
            )

        except fastf1.exceptions.RateLimitExceededError:

            print(
                " FastF1 rate limit reached while getting schedule."
            )

            if schedule_attempts < max_schedule_attempts:
                print("Waiting 60 minutes before retrying...")
                time.sleep(3600)

        except Exception as e:

            print(
                f" Could not load {year} schedule."
            )
            print(
                f"   {type(e).__name__}: {e}"
            )
            break

    if schedule is None:
        print(f" Skipping entire {year} season.")
        continue


    # ========================================================
    # 5. LOOP THROUGH RACES
    # ========================================================

    for _, event in schedule.iterrows():

        race_name = event["EventName"]

        # Ignore testing events
        if event["EventFormat"] == "testing":
            print(f"Skipping testing event: {race_name}")
            skipped_races += 1
            continue

        # ----------------------------------------------------
        # Check whether race is already in database
        # ----------------------------------------------------

        if (year, race_name) in existing_races:

            print(
                f"✓ Already in database: "
                f"{year} {race_name}"
            )

            skipped_races += 1
            continue


        print()
        print("-" * 60)
        print(f"Loading: {year} {race_name}")
        print("-" * 60)


        # ----------------------------------------------------
        # Download race
        # ----------------------------------------------------

        race_success = False
        attempts = 0
        max_attempts = 3

        while attempts < max_attempts:

            attempts += 1

            try:

                print(
                    f"Downloading race data "
                    f"(attempt {attempts}/{max_attempts})..."
                )

                # Get race session
                session = fastf1.get_session(
                    year,
                    race_name,
                    "R"
                )

                # Load race data
                print("Loading session data...")

                session.load(
                    telemetry=False,
                    weather=False,
                    messages=False
                )

                print("✓ Session loaded.")


                # ------------------------------------------------
                # Get laps
                # ------------------------------------------------

                clean_laps = (
                    session.laps
                    .pick_wo_box()
                    .copy()
                )

                if clean_laps.empty:

                    print(
                        f" No clean laps found for "
                        f"{year} {race_name}."
                    )

                    break

                print(
                    f"✓ Loaded {len(clean_laps)} clean laps."
                )


                # ------------------------------------------------
                # Convert lap times to seconds
                # ------------------------------------------------

                clean_laps["Sector1_s"] = (
                    clean_laps["Sector1Time"]
                    .dt.total_seconds()
                )

                clean_laps["Sector2_s"] = (
                    clean_laps["Sector2Time"]
                    .dt.total_seconds()
                )

                clean_laps["Sector3_s"] = (
                    clean_laps["Sector3Time"]
                    .dt.total_seconds()
                )

                clean_laps["LapTime_s"] = (
                    clean_laps["LapTime"]
                    .dt.total_seconds()
                )


                # ------------------------------------------------
                # Create driver summaries
                # ------------------------------------------------

                race_data = []

                drivers = clean_laps["Driver"].dropna().unique()

                print(
                    f"Processing {len(drivers)} drivers..."
                )

                for driver in drivers:

                    driver_laps = clean_laps[
                        clean_laps["Driver"] == driver
                    ].copy()

                    if driver_laps.empty:
                        continue


                    avg_s1 = driver_laps["Sector1_s"].mean()
                    avg_s2 = driver_laps["Sector2_s"].mean()
                    avg_s3 = driver_laps["Sector3_s"].mean()
                    avg_lap = driver_laps["LapTime_s"].mean()
                    best_lap = driver_laps["LapTime_s"].min()


                    # Team information
                    team = None

                    if "Team" in driver_laps.columns:
                        team_values = (
                            driver_laps["Team"]
                            .dropna()
                            .unique()
                        )

                        if len(team_values) > 0:
                            team = team_values[0]


                    # Speed trap
                    max_speed = None

                    if "SpeedST" in driver_laps.columns:

                        speed_values = (
                            pd.to_numeric(
                                driver_laps["SpeedST"],
                                errors="coerce"
                            )
                            .dropna()
                        )

                        if not speed_values.empty:
                            max_speed = speed_values.max()


                    race_data.append({

                        "Year": year,

                        "Race_Name": race_name,

                        "Driver": driver,

                        "Team": team,

                        "Avg_Sector1_s": (
                            round(avg_s1, 3)
                            if pd.notna(avg_s1)
                            else None
                        ),

                        "Avg_Sector2_s": (
                            round(avg_s2, 3)
                            if pd.notna(avg_s2)
                            else None
                        ),

                        "Avg_Sector3_s": (
                            round(avg_s3, 3)
                            if pd.notna(avg_s3)
                            else None
                        ),

                        "Avg_LapTime_s": (
                            round(avg_lap, 3)
                            if pd.notna(avg_lap)
                            else None
                        ),

                        "Best_LapTime_s": (
                            round(best_lap, 3)
                            if pd.notna(best_lap)
                            else None
                        ),

                        "Max_Speed_ST_kmh": max_speed,

                        "Clean_Laps_Completed": len(driver_laps)

                    })


                # ------------------------------------------------
                # Save race to database
                # ------------------------------------------------

                if not race_data:

                    print(
                        f" No driver data generated "
                        f"for {year} {race_name}."
                    )

                    break


                race_df = pd.DataFrame(race_data)

                print(
                    f"Saving {len(race_df)} drivers "
                    f"to database..."
                )

                race_df.to_sql(
                    table_name,
                    engine,
                    if_exists="append",
                    index=False
                )

                print(
                    f"✅ Successfully saved "
                    f"{year} {race_name}."
                )

                successful_races += 1

                existing_races.add(
                    (year, race_name)
                )

                race_success = True

                break


            # ----------------------------------------------------
            # Rate limit
            # ----------------------------------------------------

            except fastf1.exceptions.RateLimitExceededError:

                print(
                    "🚨 FastF1 rate limit reached."
                )

                if attempts < max_attempts:

                    print(
                        "Waiting 60 minutes before retry..."
                    )

                    time.sleep(3600)

                else:

                    print(
                        " Maximum retry attempts reached."
                    )


            # ----------------------------------------------------
            # Other errors
            # ----------------------------------------------------

            except Exception as e:

                print()
                print(
                    f"ERROR downloading "
                    f"{year} {race_name}"
                )

                print(
                    f"Error type: {type(e).__name__}"
                )

                print(
                    f"Error message: {e}"
                )

                print()

                break


        # --------------------------------------------------------
        # Race failed
        # --------------------------------------------------------

        if not race_success:

            failed_races += 1

            print(
                f"Failed to download "
                f"{year} {race_name}."
            )


        # Small delay between races
        time.sleep(2)


# ============================================================
# 6. FINAL SUMMARY
# ============================================================

print()
print("=" * 60)
print("DOWNLOAD FINISHED")
print("=" * 60)

print(f"Successful races : {successful_races}")
print(f"Failed races     : {failed_races}")
print(f"Skipped races    : {skipped_races}")

print()
print(f"Database:")
print(database_path)

print()
print("The script has finished.")
