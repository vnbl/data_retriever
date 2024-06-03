from src.initialize_db import create_postgres_tables
from src.extract.extract_data import extract_fiuna_data, extract_meteostat_data
from src.transform.transform_data import transform_fiuna_data, transform_meteostat_data
from src.load.load_data import load_station_readings_raw, load_weather_data
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main():
    create_postgres_tables()
    
    fiuna_data, extract_status = extract_fiuna_data()
    if extract_status is False:
        return 'Error: Extracting data from FIUNA failed'
    
    transformed_fiuna_data, transform_status = transform_fiuna_data(fiuna_data)
    if transform_status is False:
        return 'Error: Transforming data from FIUNA failed'
    
    load_status = load_station_readings_raw(transformed_fiuna_data)
    if load_status is False: 
        return 'Error: Loading data to StationReadingsRaw failed'
    
    logging.info('Success: Data from FIUNA loaded correctly')
    
    # Meteostat Data
    meteostat_data, extract_status = extract_meteostat_data()
    if extract_status is False:
        return 'Error: Extracting data from Meteostat failed'
    
    transformed_meteostat_data, transform_status = transform_meteostat_data(meteostat_data)
    if transform_status is False:
        return 'Error: Transforming data from Meteostat failed'
    
    load_status = load_weather_data(transformed_meteostat_data)
    if load_status is False:
        return 'Error: Loading data to WeatherData failed'
    
    logging.info('Success: Data from Meteostat loaded correctly')

    return 'Process finished correctly'
    

if __name__ == "__main__":
    message = main()
    logging.info(message)