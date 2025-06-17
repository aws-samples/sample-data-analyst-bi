import sys
sys.path.insert(0, '../')
import pandas as pd
import sqlite3
import os
import yaml
import argparse
import psycopg2
import pandas as pd 
from sqlalchemy import create_engine

DB_CONF_LOC = "../conf/db_config.yaml"
SQLITE_EXPORT_LOC = "../data/migration_csv_temp"

def export_sqllite_data (db, target_dir):
    # establish database connection
    assert db is not None, "db parameter is manadatory!"
    assert target_dir is not None, "target_dir is manadatory!"
    conn = sqlite3.connect(db, check_same_thread=False)
    try:
        df = pd.read_sql("SELECT * FROM sqlite_master WHERE type='table'", conn)
        tables = df['tbl_name'].values.tolist()

        if not os.path.exists(target_dir):
            os.makedirs(target_dir)

        for tab in tables:
            if len(tab.split(" ")) == 1:
                df = pd.read_sql(f'SELECT * from {tab}', conn)
                df.to_csv(f'{target_dir}/{tab}.csv', index = False)
            else:
                raise ValueError(f"Invalid Table Name: {tab}")
        files = [f for f in os.listdir(target_dir) if f.endswith(".csv")]
        print(f"Done! Total tables exported: {len(files)}")
        print(files)
    except Exception as e:
        raise e
    finally:
        conn.close()


def load_data_into_aws_aurora(data_dir, usr, passwd, db_uri, db_port, db_name):
    
    conn_string = f"postgresql://{usr}:{passwd}@{db_uri}:{db_port}/{db_name}"
    db = create_engine(conn_string) 
    conn = db.connect()
    try:
        files = [f for f in os.listdir(f'{data_dir}/') if f.endswith(".csv")]
        ### Load data (csv) into Aurora PostGreSQL database
        for f in files:
            tab_name = f.replace(".csv", "")
            df = pd.read_csv(f"{data_dir}/{f}")
            df.to_sql(tab_name, conn, if_exists='replace')
    except Exception as e:
        raise e
    finally:
        conn.close()

    ### Query Aurora PostGreSQL database
    conn1 = psycopg2.connect(
        database=db_name,
        user=usr,
        password=passwd,
        host=db_uri,
        port= db_port
    )
    try:
        conn1.autocommit = True
        cursor = conn1.cursor() 
        for f in files:
            tab_name = f.replace(".csv", "")
            if len(tab_name.split(" ")) == 1:
                df = pd.read_sql(f'SELECT * from {tab_name}', conn1)
                print(tab_name, df.shape)
                conn1.commit() 
            else:
                raise ValueError(f"Invalid Table Name: {tab_name}")
    except Exception as e:
        raise e
    finally:
        conn1.close()


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Process inputs.')
    parser.add_argument('db_user')
    parser.add_argument('db_password')
    args = parser.parse_args()
    
    db_user = args.db_user
    db_password = args.db_password

    with open(DB_CONF_LOC, 'r') as file:
        db_conf = yaml.safe_load(file)
    print (db_conf["PostgreSQL"])
    sqllite_db = db_conf["SQLite"]['db_conn_conf']['db_file_path']
    export_dir = SQLITE_EXPORT_LOC

    pgsql_db_uri = db_conf["PostgreSQL"]['db_conn_conf']['host']
    pgsql_db_port = db_conf["PostgreSQL"]['db_conn_conf']['port']
    pgsql_db_name = db_conf["PostgreSQL"]['db_conn_conf']['database']

    export_sqllite_data (sqllite_db, export_dir)

    files = [f for f in os.listdir(export_dir) if f.endswith(".csv")]
    print (files)

    load_data_into_aws_aurora(export_dir, db_user, db_password, pgsql_db_uri, pgsql_db_port, pgsql_db_name)

