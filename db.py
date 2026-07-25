from contextlib import contextmanager
import psycopg
from psycopg.rows import dict_row
from .config import get_settings
@contextmanager
def db_connection():
    with psycopg.connect(get_settings().database_url,row_factory=dict_row,autocommit=False) as conn: yield conn
