import asyncpg
import os
import urllib.parse
import pandas as pd
from contextlib import asynccontextmanager

# from src.langgraph.nodes import db_search 
# from src.langgraph.states import ToolState
# from langgraph.graph import  StateGraph, START, END

@asynccontextmanager
async def db_conn():
    conn = await asyncpg.connect(
        user=os.getenv('PSQL_USERNAME'),
        password=os.getenv('PSQL_PASSWORD'),
        database=os.getenv('PSQL_DATABASE'),
        host=os.getenv('PSQL_HOST')
    )
    try:
        yield conn
    finally:
        await conn.close()

def db_conninfo():
    password_encoded = urllib.parse.quote(os.getenv("PSQL_PASSWORD"))
    conninfo = (
        f"postgres://{os.getenv('PSQL_USERNAME')}:{password_encoded}"
        f"@{os.getenv('PSQL_HOST')}:{os.getenv('PSQL_PORT')}/{os.getenv('PSQL_DATABASE')}"
        f"?sslmode={os.getenv('PSQL_SSLMODE')}"
    )
    return conninfo

def db_uri(local=True):
    if local:
        password_encoded = urllib.parse.quote(os.getenv("PSQL_PASSWORD_local"))
        uri = (
        f"postgresql+psycopg2://{os.getenv('PSQL_USERNAME_local')}:{password_encoded}"
        f"@{os.getenv('PSQL_HOST_local')}:{os.getenv('PSQL_PORT_local')}/{os.getenv('PSQL_DATABASE_local')}"
        f"?sslmode={os.getenv('PSQL_SSLMODE_local')}&options=-csearch_path%3Dlangraph"
    )
        return uri
    password_encoded = urllib.parse.quote(os.getenv("PSQL_PASSWORD"))
    uri = (
    f"postgresql+psycopg2://{os.getenv('PSQL_USERNAME')}:{password_encoded}"
    f"@{os.getenv('PSQL_HOST')}:{os.getenv('PSQL_PORT')}/{os.getenv('PSQL_DATABASE')}"
    f"?sslmode={os.getenv('PSQL_SSLMODE')}&options=-csearch_path%3Dgeneral_information")
    return uri

def db_uri2():
    password_encoded = urllib.parse.quote(os.getenv("PSQL_PASSWORD"))
    uri = (
    f"postgresql://{os.getenv('PSQL_USERNAME')}:{password_encoded}"
    f"@{os.getenv('PSQL_HOST')}:{os.getenv('PSQL_PORT')}/{os.getenv('PSQL_DATABASE')}"
    f"?sslmode={os.getenv('PSQL_SSLMODE')}")
    return uri
    
def calculate_nps(df: pd.DataFrame, nps_column: str = 'nps') -> float:
    total_responses = df[nps_column].dropna().shape[0]
    if total_responses == 0:
        return 0.0  # Avoid division by zero

    promoters = df[df[nps_column] >= 9].shape[0]
    detractors = df[df[nps_column] <= 6].shape[0]

    nps_score = ((promoters - detractors) / total_responses) * 100
    return round(nps_score, 2)