from sqlalchemy import func, distinct, and_
from datetime import timedelta
from src.models import StationReadings, Regions, StationsReadingsRaw, WeatherReadings, CalibrationFactors, WeatherStations
from src.time_utils import validate_date_hour
from src.querys import query_last_stationreadings_timestamp, fetch_pattern_station_id_region
import pandas as pd

import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_raw_readings_for_feature_transformation(session, station_id, last_transformation_timestamp):
    '''
    query new readings from station_readings_raw table that need to be transformed.
    '''
    try:
        logging.info('Starting query to StationReadingsRaw...')
        raw_readings = session.query(
            StationsReadingsRaw.id,
            StationsReadingsRaw.fecha,
            StationsReadingsRaw.hora,
        ).filter(
            StationsReadingsRaw.station_id == station_id, 
            func.to_timestamp(func.concat(StationsReadingsRaw.fecha, ' ', StationsReadingsRaw.hora), 'DD-MM-YYYY HH24:MI') > last_transformation_timestamp
        ).all()

        valid_readings = [
            reading for reading in raw_readings
            if validate_date_hour(reading.fecha, reading.hora)
        ]
        
        if not valid_readings:
            logging.info('No valid readings found')
            return []

        valid_ids = [reading.id for reading in valid_readings]
        
        # Split valid_ids into chunks
        chunk_size = 1000  # Adjust chunk size as needed
        chunks = [valid_ids[i:i + chunk_size] for i in range(0, len(valid_ids), chunk_size)]
        
        final_readings = []
        for chunk in chunks:
            chunk_readings = session.query(StationsReadingsRaw).filter(
                and_(
                    StationsReadingsRaw.id.in_(chunk),
                    func.to_timestamp(func.concat(StationsReadingsRaw.fecha, ' ', StationsReadingsRaw.hora), 'DD-MM-YYYY HH24:MI') >= last_transformation_timestamp,
                )
            ).all()
            final_readings.extend(chunk_readings)
        
        logging.info(f'Retrieved {len(final_readings)} readings after filtering by timestamp')
        return final_readings

    except Exception as e:
        logging.error(f'An error occurred while fetching raw readings: {e}')
        return None
    
def convert_readings_to_dataframe(raw_readings):
    '''
    Select relevant features and convert readings to dataframe
    '''
    relevant_attributes = [ 'fecha', 'hora', 'mp2_5', 'mp10', 'mp1', 'temperatura', 'humedad', 'presion', 'station_id']
    records =[{attr: getattr(reading, attr) for attr in relevant_attributes} for reading in raw_readings]
    df = pd.DataFrame(records)
    return df

def add_date_column_as_index(df):
    '''
    Converts 'fecha' and 'hora' (VARCHAR) columns in dataframe to
    'date' datetime column.
    '''
    df['date'] = df['fecha'] + ' ' + df['hora']
    df['date'] = pd.to_datetime(df['date'], format = '%d-%m-%Y %H:%M', errors = 'coerce')
    df.set_index('date', inplace = True)
    return df.drop(columns = ['fecha', 'hora'], axis = 1)
    
def rename_columns(df, renaming_dict):
    '''
    rename station_readings_raw columns to station_readings columns
    '''
    return df.rename(columns = renaming_dict)

def change_dtype_to_numeric(df, numeric_columns):
    df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors='coerce')
    return df

def change_raw_readings_frequency(df):
    '''
    change dataframe frequency to 1 hour.
    '''

    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError('The Dataframe index must be a DatetimeIndex')

    df.index = df.index.floor('h')
    
    df = df.groupby(df.index).agg({
        'pm1': 'mean',
        'pm2_5': 'mean',
        'pm10': 'mean',
        'temperature': 'mean',
        'humidity': 'mean',
        'pressure': 'mean'
    }).round(2)

    return df

def add_station_column(df, station_id):
    df['station'] = station_id
    df['station'] = df['station'].astype(int)
    return df

def get_calibration_timerange(df):
    start = df.index.min()
    end = df.index.max()
    return start, end

def get_humidity_dataframe_from_weather_readings(session, station_id, start, end):
    '''
    get humidity readings for calibration
    '''
    _, region = fetch_pattern_station_id_region(session, station_id)

    humidity_readings = session.query(
        WeatherReadings.date, 
        WeatherReadings.humidity
        ).join(
            WeatherStations, WeatherReadings.weather_station == WeatherStations.id
        ).join(
            Regions, WeatherStations.region == Regions.region_code
        ).filter(
            Regions.region_code == region,
            WeatherReadings.date >= start,
            WeatherReadings.date <= end 
    ).all()

    if not humidity_readings:
        return None
    else:
        humidity_df = pd.DataFrame([{'date': reading.date, 'region_humidity' : reading.humidity} for reading in humidity_readings])
        humidity_df.set_index('date', inplace = True)
        return humidity_df

def expand_calibration_factors_dataframe(df):
    '''
    Convert calibration_factor readings for calibration.

    '''

    df['date_range'] = df.apply(lambda row: pd.date_range(start=row['date_start'], end=row['date_end'], freq='h'), axis=1)
    expanded_df = df.explode('date_range').reset_index(drop=True)

    expanded_df = expanded_df.rename(columns={'date_range': 'date'})[['date', 'calibration_factor']]
    expanded_df.set_index('date', inplace = True)
    
    return expanded_df

def get_calibration_factors_dataframe(session, station_id, start, end): # sacar 'dataframe' de todas mis funciones
    '''
    retrieve relevant calibration factors for calibration
    '''
    
    readings = session.query(
        CalibrationFactors.date_start,
        CalibrationFactors.date_end,
        CalibrationFactors.calibration_factor
    ).filter(
        CalibrationFactors.station_id == station_id,
        CalibrationFactors.date_start <= end,
        CalibrationFactors.date_end >= start
    ).all()

    if not readings:
        calibration_df = pd.DataFrame([{'date_start' : start,
                                        'date_end' : end,
                                        'calibration_factor': 1}])
    else:
        calibration_df = pd.DataFrame([{'date_start': reading.date_start, 
                                    'date_end' : reading.date_end,
                                    'calibration_factor': reading.calibration_factor} for reading in readings])

    calibration_df = expand_calibration_factors_dataframe(calibration_df)
    #calibration_df.to_csv('get_calibration.csv')
    return calibration_df

def apply_calibration_factor(df, pm_columns, humidity_df, calibration_df):
    '''
    Calibrate PM readings using humidity data from weather_readings and
    calibration factors from calibration_factors table.
    '''
    df_merged = df.join(humidity_df, how = 'left').join(calibration_df, how = 'left')
    df_merged['calibration_factor'] = df_merged['calibration_factor'].fillna(1)
    df_merged['C_RH'] = df_merged['region_humidity'].apply(lambda x: 1 if x < 65 else (0.0121212*x) + 1 if x < 85 else (1 + ((0.2/1.65)/(-1 + 100/min(x, 90)))))
    
    for pm in pm_columns:
        df_merged[pm] = (df_merged[pm] / df_merged['C_RH']) * df_merged['calibration_factor']

    df_merged = df_merged.round(2)
    df_merged.drop(columns=['region_humidity', 'C_RH', 'calibration_factor'], inplace=True)
    df_merged.sort_index(ascending=True, inplace=True)
    df_merged.reset_index(inplace=True)

    return df_merged

def transform_raw_readings_to_station_readings(session, station_id):
    '''
    Transform readings from station_readings_raw to readings for station_readings
    for a single station.
    '''
    # setup
    renaming_dict = {'mp1': 'pm1',
                    'mp2_5': 'pm2_5',
                    'mp10': 'pm10',
                    'temperatura': 'temperature',
                    'humedad': 'humidity',
                    'presion': 'pressure'}

    numeric_columns = ['pm1', 'pm2_5', 'pm10', 'temperature', 'humidity', 'pressure']

    last_transformation_timestamp = query_last_stationreadings_timestamp(session, station_id)
    raw_station_readings = get_raw_readings_for_feature_transformation(session, station_id, last_transformation_timestamp)

    if raw_station_readings is not None:
        #basic transformations
        df = convert_readings_to_dataframe(raw_station_readings)
        df = add_date_column_as_index(df)
        df = rename_columns(df, renaming_dict)
        df = change_dtype_to_numeric(df, numeric_columns)
        df = change_raw_readings_frequency(df)

        # pm calibration
        pm_columns = ['pm1', 'pm2_5', 'pm10'] # parameters to calibrate
        start, end = get_calibration_timerange(df)
        
        humidity_df = get_humidity_dataframe_from_weather_readings(session, station_id, start, end)
        if humidity_df is None:
            return None, 'no humidity data for calibration'
        
        calibration_df = get_calibration_factors_dataframe(session, station_id, start, end) 
        if calibration_df is None:
            return None, f'no valid calibration factors for station {station_id}'

        df = apply_calibration_factor(df, pm_columns, humidity_df, calibration_df)
        df = add_station_column(df, station_id)

        return df, last_transformation_timestamp, f'basic transformations and pm calibration success.'

def upsert_station_readings_into_db(session, df):
    '''
    Update or insert new transformed readings into db.

    Update old readings: 
    - Check for readings that need to be updated because of new information in
    StationReadingsRaw.
    - Set reading values (pm1, pm2_5, pm10, temperature, humidity,
    pressure) to new recalculated values.
    - Set calculated values (aqi, statistical features) to None to recalculate
    later on.
    
    Insert new transformed readings:
    - Check if incoming reading is new reading or update reading.
    - Insert only new readings into db to avoid duplicates.

    '''

    records = df.to_dict(orient='records') 
    
    stations = {record['station'] for record in records}
    dates = {record['date'] for record in records}

    # check existing records that need to be updated
    existing_records = session.query(StationReadings).filter(
        StationReadings.station.in_(stations),
        StationReadings.date.in_(dates)
    ).all()

    # dictionary of existing records that need to be updated
    # with key = (station, date) and value = information about reading.
    existing_records_dict = {(existing_record.station, existing_record.date): existing_record for existing_record in existing_records}

    # update old records if needed
    for record in records:
        key = (record['station'], record['date'])
        if key in existing_records_dict:
            existing_record = existing_records_dict[key]
            existing_record.pm1 = record['pm1']
            existing_record.pm2_5 = record['pm2_5']
            existing_record.pm10 = record['pm10']
            existing_record.temperature = record['temperature']
            existing_record.humidity = record['humidity']
            existing_record.pressure = record['pressure']
            # Set aqi and statistical features to None to recalculate
            # values using updated pm values.
            existing_record.aqi_pm2_5 = None
            existing_record.aqi_pm10 = None
            existing_record.level = None
            
            existing_record.pm2_5_avg_6h = None
            existing_record.pm2_5_max_6h = None
            existing_record.pm2_5_skew_6h = None
            existing_record.pm2_5_std_6h = None

            existing_record.aqi_pm2_5_max_24h = None
            existing_record.aqi_pm2_5_skew_24h = None
            existing_record.aqi_pm2_5_std_24h = None
            
    # create a list of StationReadings objects with the new records for insertion
    new_records = [StationReadings( date = record['date'],
                                    station = record['station'],
                                    pm1 = record['pm1'],
                                    pm2_5 = record['pm2_5'],
                                    pm10 = record['pm10'],
                                    temperature = record['temperature'],
                                    humidity = record['humidity'],
                                    pressure = record['pressure']
                                ) 
                                # check that record is not in existing_record_dict
                                for record in records if (record['station'], record['date']) not in existing_records_dict
                            ]
    
    session.add_all(new_records)
    session.commit() # commit new records
    return True