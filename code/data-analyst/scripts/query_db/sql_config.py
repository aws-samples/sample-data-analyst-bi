# config.py

# SQLite configuration
SQLITE_CONFIG = {
    'db_type': 'sqlite',
    'database': '/home/sagemaker-user/data_analyst_bot/da_refactor/db_data/database/data/sql_reasoningv2.db'
}

# MySQL configuration
MYSQL_CONFIG = {
    'db_type': 'mysql',
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',
    'database': 'your_database',
    'port': 3306
}

# PostgreSQL configuration
POSTGRESQL_CONFIG = {
    'db_type': 'postgresql',
    'host': 'query-bot-project-test.cluster-chwgu0qgilza.us-east-1.rds.amazonaws.com',
    'user': 'demo',
    'password': 'pass123',
    'database': 'sales',
    'port': 5432
}

# You can add more configurations as needed
# Select the active configuration
ACTIVE_DB_CONFIG = POSTGRESQL_CONFIG
