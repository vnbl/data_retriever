import pandas as pd
import numpy as np

if 'transformer' not in globals():
    from mage_ai.data_preparation.decorators import transformer
if 'test' not in globals():
    from mage_ai.data_preparation.decorators import test

def combine_existing_and_new_readings(df1, df2):
    df_combined = pd.concat([df1, df2], ignore_index=True)
    df_combined['date_utc'] = pd.to_datetime(df_combined['date_utc'], errors='coerce')
    return df_combined

def drop_bad_readings(df):
    df['pm2_5'] = df['pm2_5'].replace(-999, np.nan)
    return df

def interpolate_missing_data(df):
    
    # Perform interpolation for numerical columns
    df_interpolated = df.copy()
    df_interpolated['pm2_5'] = df_interpolated['pm2_5'].interpolate(method='linear', limit_direction='both')
    # Forward and backward fill for wind_dir
    df_interpolated['station_id'] = df['station_id'].bfill().ffill()
    
    # Fill NaN values in data_source with 'interpolated'
    df_interpolated['data_source'].fillna('interpolated', inplace=True)
    
    # Reset index to ensure date_utc is a column
    df_interpolated = df_interpolated.reset_index()
    
    return df_interpolated

def set_variable_dtypes(df):
    try:
        df = df.astype({
            'measurement_id': 'Int64',  # Use 'Int64' for nullable integers
            'pm2_5': 'float',
            'station_id': 'int'
        })
        df['date_utc'] = pd.to_datetime(df['date_utc'])
    except Exception as e:
        print(f"Error in setting variable types: {e}")
    return df

def process_weather_silver(group):
    group.drop_duplicates(subset=['date_utc'], keep='first', inplace=True)
    group = drop_bad_readings(group)
    group.set_index('date_utc', inplace=True)
    group['data_source'] = 'raw' 
    
    group = group.resample('h').asfreq()
    
    group = interpolate_missing_data(group)
    
    group = set_variable_dtypes(group)
    group.sort_values(by=['date_utc'], ascending=True, inplace=True)

    return group

@transformer
def transform(data, data_2, *args, **kwargs):
    if not data_2.empty:
        group = combine_existing_and_new_readings(data, data_2)
    else:
        group = data.copy()

    processed_data = group.groupby('station_id').apply(process_weather_silver).reset_index(drop=True)

    if not data_2.empty:
        data_2_filtered = data_2[['station_id', 'date_utc']]
        processed_data = processed_data.merge(data_2_filtered, on=['station_id', 'date_utc'], how='left', indicator=True)
        processed_data = processed_data[processed_data['_merge'] == 'left_only'].drop(columns=['_merge'])
    
    return processed_data

@test
def test_output(output, *args) -> None:
    """
    Template code for testing the output of the block.
    """
    assert output is not None, 'The output is undefined'