from mage_ai.settings.repo import get_repo_path
from mage_ai.io.config import ConfigFileLoader
from mage_ai.io.postgres import Postgres
from pandas import DataFrame
from os import path

if 'data_exporter' not in globals():
    from mage_ai.data_preparation.decorators import data_exporter

def get_table_columns(schema_name, table_name, config_path, config_profile='default'):
    with Postgres.with_config(ConfigFileLoader(config_path, config_profile)) as loader:
        query = f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = '{schema_name}' AND table_name = '{table_name}'
        ORDER BY ordinal_position;
        """
        columns = loader.load(query)
        column_list = columns['column_name'].tolist()
        # Filter out 'id' column if it exists
        column_list = [col for col in column_list if col.lower() != 'id']
        print (column_list)
        return column_list


def reorder_dataframe_columns(df, columns_order):
    return df[columns_order]

@data_exporter
def export_data_to_postgres(df: DataFrame, **kwargs) -> None:
    """
    Template for exporting data to a PostgreSQL database.
    Specify your configuration settings in 'io_config.yaml'.

    Docs: https://docs.mage.ai/design/data-loading#postgresql
    """

    schema_name = 'public'  # Specify the name of the schema to export data to
    table_name = 'airnow_readings_bronze'  # Specify the name of the table to export data to
    config_path = path.join(get_repo_path(), 'io_config.yaml')
    config_profile = 'default'

    columns_order = get_table_columns(schema_name, table_name, config_path, config_profile)

    df = reorder_dataframe_columns(df, columns_order)

    with Postgres.with_config(ConfigFileLoader(config_path, config_profile)) as loader:
        print(f"Exporting data to table: {schema_name}.{table_name} with columns: {df.columns.tolist()}")
        loader.export(
            df,
            schema_name,
            table_name,
            index=False,  # Specifies whether to include index in exported table
            if_exists='append',  # Specify resolution policy if table name already exists
        )