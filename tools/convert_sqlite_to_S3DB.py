
import sqlite3
import pandas as pd
import os

def extract_tables_to_organized_csv(db_path, base_output_dir):
    """
    Extract tables from SQLite database and save as CSV files in separate folders.
    
    Args:
        db_path (str): Path to the SQLite database file
        base_output_dir (str): Base directory where table folders will be created
    """
    try:
        # Create base output directory if it doesn't exist
        if not os.path.exists(base_output_dir):
            os.makedirs(base_output_dir)
            print(f"Created base directory: {base_output_dir}")
        
        # Connect to the SQLite database
        conn = sqlite3.connect(db_path)
        print(f"Connected to database: {db_path}")
        
        # Get list of all tables in the database
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        if not tables:
            print("No tables found in the database.")
            return
        
        # Extract each table to a CSV file in its own folder
        for table in tables:
            table_name = table[0]
            
            # Create folder for this table
            table_folder = os.path.join(base_output_dir, table_name)
            if not os.path.exists(table_folder):
                os.makedirs(table_folder)
            
            try:
                # Read the table into a pandas DataFrame
                df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
                
                # Create CSV filename
                csv_path = os.path.join(table_folder, f"{table_name}.csv")
                
                # Save to CSV
                df.to_csv(csv_path, index=False)
                print(f"Successfully exported {table_name} to {csv_path}")
                print(f"Number of records exported: {len(df)}")
                
            except Exception as e:
                print(f"Error processing table {table_name}: {str(e)}")
                continue
        
    except sqlite3.Error as e:
        print(f"SQLite error: {str(e)}")
    except Exception as e:
        print(f"An error occurred: {str(e)}")
    finally:
        # Close the connection
        if 'conn' in locals():
            conn.close()
            print("Database connection closed.")

def main():
    # Configuration
    database_path = "student_club.sqlite"  # Replace with your database path
    output_directory = "exported_tables"  # Replace with your desired output directory
    
    print("Starting data extraction process...")
    extract_tables_to_organized_csv(database_path, output_directory)
    print("Process completed!")

if __name__ == "__main__":
    main()
