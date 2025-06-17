import logging
import sqlite3
import psycopg2
from abc import ABC, abstractmethod
import pandas as pd
import json
import os
import re
from decimal import Decimal
from scripts.utils import s3

logger = logging.getLogger(__name__)


class DatabaseHelper(ABC):
    supported_databases = ["sqlite", "postgresql", "redshift"]

    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        llm_id: str,
        llm_params: dict
    ) -> None:
        super().__init__()
        if database not in self.supported_databases:
            raise ValueError(
                f"Error: {database} not in supported databases {self.supported_databases}"
            )
        self.database = database
        self.db_conn_conf = db_conn_conf
        self.llm_id = llm_id
        self.llm_params = llm_params

    def proceed_with_sql(self, sql):
        if sql.strip().upper().startswith("SELECT") or sql.strip().upper().startswith("WITH"):
            return True
        else:
            return False

    @abstractmethod
    def _excute(self, command: str) -> pd.DataFrame:
        pass

    @abstractmethod
    def close_conn(self) -> None:
        pass


class SQLiteHelper(DatabaseHelper):
    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        llm_id: str,
        llm_params: dict
    ):
        super().__init__(
            database, db_conn_conf, llm_id, llm_params
        )
        if "db_file_path" not in db_conn_conf.keys():
            raise ValueError(
                "Error: 'db_file_path' is required to load SQLite database!"
            )
        db_file = db_conn_conf["db_file_path"]
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        try:
            self.cursor = self.conn.cursor()
        except Exception as e:
            self.conn.close()
            raise e

    def _excute(self, command):
        if self.proceed_with_sql(command):
            try:
                result = pd.read_sql(command, self.conn)
            except Exception as e:
                """Format the error message"""
                logging.info(e)
                result = f"{e}"
        else:
            result = "Error: Generated SQL not valid! Please retry with a different question."

        return result

    def run_sql(self, question: str, command: str) -> tuple[pd.DataFrame | str, str]:
        result = self._excute(command)
        print("first result", result)
        return result, command

    def close_conn(self):
        self.conn.close()


class PostgreSQLHelper(DatabaseHelper):
    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        llm_id: str,
        llm_params: dict
    ):
        super().__init__(
            database, db_conn_conf, llm_id, llm_params
        )
        self.conn = psycopg2.connect(
            database=db_conn_conf["database"],
            user=db_conn_conf["user"],
            password=db_conn_conf["password"],
            host=db_conn_conf["host"],
            port=db_conn_conf["port"],
        )
        try:
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
        except Exception as e:
            print('PostgreSQLHelper:', e)
            self.conn.close()

    def preprocess_sql(self, sql):
        possible_cases = [
            " id ",
            ".id ",
            " id,",
            ",id ",
            ".id,",
            ",id)",
            " id)",
            ".id)",
            "(id ",
            "(id,",
            "(id)",
            " id\n",
            "(id\n",
            ",id\n",
        ]
        sql = sql.lower()
        for c in possible_cases:
            if c in sql:
                sql = sql.replace(c, c.replace("id", '"id"'))
                print(c, "replaced", sql)
        return sql.upper()

    def _excute(self, command: str) -> pd.DataFrame:
        command = self.preprocess_sql(command)
        if self.proceed_with_sql(command):
            try:
                result = pd.read_sql(command, self.conn)
                result = result.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
            except Exception as e:
                """Format the error message"""
                logging.info(e)
                result = f"{e}"
        else:
            result = "Error: Generated SQL not valid! Please retry with a different question."
        return result

    def run_sql(
        self, question: str, command: str
    ) -> tuple[pd.DataFrame | str, str]:
        if command.strip().upper().startswith("SELECT ") or command.strip().upper().startswith("WITH "):
            print("INSIDE IF")
        else:
            print("INSIDE ELSE")
        result = self._excute(command)
        print("SQL execution result:", result)
        return result, command

    def close_conn(self):
        self.conn.close()


class RedshiftHelper(DatabaseHelper):
    def __init__(
        self,
        database: str,
        db_conn_conf: dict[str, str],
        llm_id: str,
        llm_params: dict
    ):
        super().__init__(
            database, db_conn_conf, llm_id, llm_params
        )
        self.conn = psycopg2.connect(
            database=db_conn_conf["database"],
            user=db_conn_conf["user"],
            password=db_conn_conf["password"],
            host=db_conn_conf["host"],
            port=db_conn_conf["port"],
        )
        try:
            self.conn.autocommit = True
            self.cursor = self.conn.cursor()
        except Exception as e:
            print('RedshiftHelper:', e)
            self.conn.close()

    def preprocess_sql(self, sql):
        possible_cases = [
            " id ",
            ".id ",
            " id,",
            ",id ",
            ".id,",
            ",id)",
            " id)",
            ".id)",
            "(id ",
            "(id,",
            "(id)",
            " id\n",
            "(id\n",
            ",id\n",
        ]
        sql = sql.lower()
        for c in possible_cases:
            if c in sql:
                sql = sql.replace(c, c.replace("id", '"id"'))
                print(c, "replaced", sql)
        return sql.upper()

    def _excute(self, command: str) -> pd.DataFrame:
        command = self.preprocess_sql(command)
        if self.proceed_with_sql(command):
            try:
                # Using cursor.execute() instead of pd.read_sql for better Redshift compatibility
                # result = pd.read_sql(command, self.conn)
                # result = result.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
                self.cursor.execute(command)
                columns = [desc[0] for desc in self.cursor.description]
                result = pd.DataFrame(self.cursor.fetchall(), columns=columns)
                result = result.applymap(lambda x: float(x) if isinstance(x, Decimal) else x)
            except Exception as e:
                logging.info(e)
                result = f"{e}"
        else:
            result = "Error: Generated SQL not valid! Please retry with a different question."
        return result

    def run_sql(
        self, question: str, command: str
    ) -> tuple[pd.DataFrame | str, str]:
        if command.strip().upper().startswith("SELECT ") or command.strip().upper().startswith("WITH "):
            print("INSIDE IF")
        else:
            print("INSIDE ELSE")
        result = self._excute(command)
        print("SQL execution result:", result)
        return result, command

    def close_conn(self):
        self.conn.close()


def get_database_helper(
    database: str,
    db_conn_conf: dict[str, str],
    llm_id: str,
    llm_params: dict,
) -> DatabaseHelper:
    database = database.strip().lower()
    if database == "sqlite":
        return SQLiteHelper(
            database,
            db_conn_conf,
            llm_id,
            llm_params
        )
    elif database == "postgresql":
        return PostgreSQLHelper(
            database,
            db_conn_conf,
            llm_id,
            llm_params
        )
    elif database == "redshift":
        return RedshiftHelper(
            database,
            db_conn_conf,
            llm_id,
            llm_params
        )
    else:
        raise ValueError(
            f"Error: {database} not in supported databases {DatabaseHelper.supported_databases}"
        )