from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import os
from dotenv import load_dotenv

try:
    load_dotenv()
except:
    raise "Error loading .env file"


def create_postgres():
    POSTGRES_USER = os.getenv('POSTGRES_USER')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
    POSTGRES_DATABASE = os.getenv('POSTGRES_DATABASE')
    POSTGRES_HOST = os.getenv('POSTGRES_HOST')
    
    postgres_engine = create_engine(f'postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}/{POSTGRES_DATABASE}')

    return postgres_engine


def create_mysql():
    MYSQL_HOST = os.getenv('MYSQL_HOST')
    MYSQL_USER = os.getenv('MYSQL_USER')
    MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
    MYSQL_DATABASE = os.getenv('MYSQL_DATABASE')
    MYSQL_TABLES = os.getenv('MYSQL_TABLES')

    mysql_engine = create_engine(f'mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}/{MYSQL_DATABASE}')

    return mysql_engine


def create_postgres_session(postgres_engine = create_postgres()):
    Session = sessionmaker(bind=postgres_engine)
    return Session()


def create_mysql_session(mysql_engine = create_mysql()):
    Session = sessionmaker(bind=mysql_engine)
    return Session()

