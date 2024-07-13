from sqlalchemy import MetaData, Table, select
from sqlalchemy.exc import SQLAlchemyError
from src.models import WeatherReadings
from src.querys import (get_weather_station_coordinates, 
                        get_last_weather_station_timestamp, 
                        get_station_readings_count,
                        get_last_station_readings_timestamp,
                        get_region_bbox,
                        get_station_region_code)
from src.time_utils import convert_to_utc
from datetime import datetime, timedelta
from pytz import timezone, utc
from meteostat import Point, Hourly
import os
from dotenv import load_dotenv
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def select_new_records_from_fiuna(mysql_engine, table_name, last_measurement_id):
    logging.info(f'Starting select_new_records_from_origin_table where table_name = {table_name} and last_measurement_id = {last_measurement_id}')

    try:
        metadata = MetaData()
        metadata.reflect(bind=mysql_engine)
        table = Table(table_name, metadata, autoload_with=mysql_engine)
        
        column_names = [column.name for column in table.columns]
        column_expressions = [column for column in table.columns]
        query = select(*column_expressions).where(table.c.ID > last_measurement_id)

        with mysql_engine.connect() as connection:
            result = connection.execute(query)
            records_as_dicts = [dict(zip(column_names, row)) for row in result.fetchall()]
        records_as_dicts_lower = [{key.lower(): value for key, value in record.items()} for record in records_as_dicts]

        logging.info(f'Selected {len(records_as_dicts_lower)} new records from table {table_name}')
        #print(records_as_dicts_lower)
        return records_as_dicts_lower
    except SQLAlchemyError as e:
        logging.error(f"Error occurred: {e}")
        return None

# meteostat_data.py

def fetch_meteostat_data(session, start, end, station_id):
    logging.info('fetching meteostat data...')
    latitude, longitude = get_weather_station_coordinates(session, station_id)
    coordinates = Point(latitude, longitude, 101)
    data = Hourly(coordinates, start, end).fetch()
    return data


def determine_meteostat_query_time_range(session, station_id):
    if session.query(WeatherReadings).count() == 0:
        start_utc = datetime(2019, 1, 1, 0, 0, 0, 0)   
    else:
        last_meteostat_timestamp = get_last_weather_station_timestamp(session, station_id)
        start_utc = convert_to_utc(last_meteostat_timestamp + timedelta(hours=1))
    
    end_utc = datetime.now(timezone('UTC')).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    
    return start_utc, end_utc


# airnow data

def define_airnow_api_url(session, pattern_station_id):
    try:
        load_dotenv()
    except:
        raise "Error loading .env file right now"
    
    station_readings_count = get_station_readings_count(session, pattern_station_id)

    if station_readings_count < 1:
        start_timestamp_utc = datetime(2023, 1, 1, 0, 0, 0, 0)
    else:
        last_airnow_timestamp_localtime = get_last_station_readings_timestamp(session, pattern_station_id) + timedelta(hours=1)
        start_timestamp_utc = convert_to_utc(last_airnow_timestamp_localtime).replace(tzinfo=utc)

    end_timestamp_utc = datetime.now(timezone('UTC'))

    if start_timestamp_utc.replace(tzinfo=utc).strftime('%Y-%m-%d %H') > end_timestamp_utc.strftime('%Y-%m-%d %H'):
        return None

    region_code = get_station_region_code(session, station_id = pattern_station_id)
    
    options = {}
    options["url"] = "https://airnowapi.org/aq/data/"
    options["start_date"] = start_timestamp_utc.strftime('%Y-%m-%d')
    options["start_hour_utc"] = start_timestamp_utc.strftime('%H')
    options["end_date"] = end_timestamp_utc.strftime('%Y-%m-%d')
    options["end_hour_utc"] = end_timestamp_utc.strftime('%H')
    options["parameters"] = "pm25"
    options["bbox"] = get_region_bbox(session, region_code)
    options["data_type"] = "c" # options: a (AQI), b (concentrations & AQI), c (concentrations)
    options["format"] = "application/json" # options: 'text/csv', 'application/json', 'application/vnd.google-earth.kml', 'application/xml'
    options["api_key"] = os.getenv('AIRNOW_API_KEY')
    options["verbose"] = 1
    options["includerawconcentrations"] = 1


    # API request URL
    request_url = options["url"] \
                  + "?startdate=" + options["start_date"] \
                  + "t" + options["start_hour_utc"] \
                  + "&enddate=" + options["end_date"] \
                  + "t" + options["end_hour_utc"] \
                  + "&parameters=" + options["parameters"] \
                  + "&bbox=" + options["bbox"] \
                  + "&datatype=" + options["data_type"] \
                  + "&format=" + options["format"] \
                  + "&api_key=" + options["api_key"]
    
    return request_url


