
import os
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# 1) Create the SQLAlchemy engine with optimized connection pooling
# -------------------------------------------------------------------------
server   = 'localhost'
username = os.environ['CRMSrvUs']
password = os.environ['CRMSrvPs']
database = os.environ['CRMSrvDb']

connection_string = (
    f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
)

# Optimized engine with connection pooling for deadlock prevention
engine = create_engine(
    connection_string,
    poolclass=QueuePool,
    pool_size=5,  # Reduced pool size to prevent connection exhaustion
    max_overflow=10,
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,   # Recycle connections every hour
    echo=False
)

# -------------------------------------------------------------------------
# 2) Helper function to execute a SQL query and return a DataFrame
# -------------------------------------------------------------------------
def get_db_data(query, params=None) -> pd.DataFrame:
    """
    Executes a SQL query and returns the result as a DataFrame.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with engine.connect() as conn:
                df = pd.read_sql_query(text(query), conn, params=params)
            return df
        except Exception as ex:
            logger.warning(f"SQL execution error (attempt {attempt + 1}/{max_retries}): {ex}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                logger.error(f"Final SQL execution error: {ex}")
                return pd.DataFrame()

# -------------------------------------------------------------------------
# 3) Function to get a list of valid InquiryID values for a given franchise.
# -------------------------------------------------------------------------
def get_inquiry_list(franchise_id) -> list:
    """
    Fetch a list of all valid InquiryID values for the specified franchise.
    """
    query = """
        SELECT DISTINCT InquiryID
        FROM tblStudents
        WHERE FranchiseID = :franchise_id
        ORDER BY InquiryID;
    """
    df = get_db_data(query, params={"franchise_id": franchise_id})
    return df["InquiryID"].tolist()

# -------------------------------------------------------------------------
# 4) Optimized function to call the stored procedure with retry logic
# -------------------------------------------------------------------------
def get_sproc_data(inquiry_id: int, max_retries: int = 3) -> Optional[Dict]:
    """
    Calls dbo.USP_Report_AccountBalance(inquiry_id) with retry logic and proper resource management.
    Returns consolidated data dictionary or None if failed.
    """
    sp_call = "{CALL dbo.USP_Report_AccountBalance(?)}"
    
    for attempt in range(max_retries):
        try:
            with engine.connect() as sql_conn:
                # Use the underlying pyodbc connection to create a cursor.
                pyodbc_conn = sql_conn.connection
                cursor = pyodbc_conn.cursor()
                
                try:
                    # Execute the stored procedure with timeout
                    cursor.execute(sp_call, (inquiry_id,))
                    
                    # Skip the first result set (starting balance).
                    cursor.nextset()
                    
                    # Retrieve the second result set: hours data.
                    hours_data = cursor.fetchall()
                    hours_dict = {}
                    if hours_data:
                        hours_columns = [desc[0] for desc in cursor.description]
                        hours_dict = dict(zip(hours_columns, hours_data[0]))
                    
                    # Move to the third result set: name data.
                    cursor.nextset()
                    name_data = cursor.fetchall()
                    name_dict = {}
                    if name_data:
                        name_columns = [desc[0] for desc in cursor.description]
                        name_dict = dict(zip(name_columns, name_data[0]))
                    
                    # Merge the two dictionaries.
                    consolidated_data = {**hours_dict, **name_dict}
                    consolidated_data["InquiryID"] = inquiry_id
                    
                    return consolidated_data
                    
                finally:
                    cursor.close()
                    pyodbc_conn.commit()
                    
        except Exception as e:
            logger.warning(f"Error processing inquiry {inquiry_id} (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(1 + attempt)  # Progressive delay
            else:
                logger.error(f"Final error processing inquiry {inquiry_id}: {e}")
                return None

# -------------------------------------------------------------------------
# 5) Batch processing function
# -------------------------------------------------------------------------
def process_inquiry_batch(inquiry_batch: List[int]) -> List[Dict]:
    """
    Process a batch of inquiries sequentially to avoid overwhelming the database.
    """
    results = []
    for inquiry_id in inquiry_batch:
        logger.info(f"Processing inquiry {inquiry_id}...")
        result = get_sproc_data(inquiry_id)
        if result is not None:
            results.append(result)
        else:
            logger.warning(f"Skipping inquiry {inquiry_id} due to error.")
        
        # Small delay between calls to prevent overwhelming the database
        time.sleep(0.1)
    
    return results

# -------------------------------------------------------------------------
# 6) Main script logic with batching and parallel processing
# -------------------------------------------------------------------------
def main(franchise_id, batch_size: int = 1000, max_workers: int = 3):
    """
    Main function that processes inquiries for a given franchise_id with batching and threading.
    
    Parameters:
        franchise_id (int): The franchise ID to use for fetching data.
        batch_size (int): Number of inquiries to process in each batch.
        max_workers (int): Maximum number of concurrent threads.
        
    Returns:
        pd.DataFrame: DataFrame with the consolidated data.
    """
    logger.info(f"Starting processing for franchise {franchise_id}")
    
    inquiry_ids = get_inquiry_list(franchise_id)
    total_inquiries = len(inquiry_ids)
    logger.info(f"Found {total_inquiries} inquiries.")
    
    if not inquiry_ids:
        logger.warning("No inquiries found.")
        return pd.DataFrame()
    
    # Split inquiries into batches
    inquiry_batches = [
        inquiry_ids[i:i + batch_size] 
        for i in range(0, len(inquiry_ids), batch_size)
    ]
    
    logger.info(f"Processing {len(inquiry_batches)} batches with {max_workers} workers")
    
    consolidated_rows = []
    processed_count = 0
    
    # Process batches with limited concurrency
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all batches
        future_to_batch = {
            executor.submit(process_inquiry_batch, batch): batch 
            for batch in inquiry_batches
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_batch):
            batch = future_to_batch[future]
            try:
                batch_results = future.result()
                consolidated_rows.extend(batch_results)
                processed_count += len(batch)
                logger.info(f"Completed batch. Progress: {processed_count}/{total_inquiries}")
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
    
    if not consolidated_rows:
        logger.warning("No data was retrieved.")
        return pd.DataFrame()
    
    df = pd.DataFrame(consolidated_rows)
    logger.info(f"Data retrieval complete. Retrieved {len(df)} records. Returning consolidated DataFrame.")
    return df

if __name__ == "__main__":
    # Example: Pass a default franchise_id here when running directly.
    franchise_id = 87  # Replace with your desired franchise ID
    df_result = main(franchise_id, batch_size=1000, max_workers=2)  # Conservative settings
    
    if df_result is not None and not df_result.empty:
        logger.info(f"Successfully processed {len(df_result)} records")
        # You can now perform additional operations with df_result if needed.
    else:
        logger.warning("No data was processed")
