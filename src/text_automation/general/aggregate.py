from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional

import pandas as pd
from sqlalchemy import text

from ..db.sql import get_engine, get_db_data

logger = logging.getLogger(__name__)


def get_inquiry_list(franchise_id: int) -> list[int]:
    q = (
        "SELECT DISTINCT InquiryID FROM tblStudents "
        "WHERE FranchiseID = :franchise_id ORDER BY InquiryID"
    )
    df = get_db_data(q, params={"franchise_id": franchise_id})
    return df["InquiryID"].astype(int).tolist() if not df.empty else []


def _sproc_account_balance(inquiry_id: int, max_retries: int = 3) -> Optional[Dict]:
    sp_call = "{CALL dbo.USP_Report_AccountBalance(?)}"
    engine = get_engine()
    for attempt in range(max_retries):
        try:
            with engine.connect() as sql_conn:
                pyodbc_conn = sql_conn.connection  # raw ODBC connection
                cursor = pyodbc_conn.cursor()
                try:
                    cursor.execute(sp_call, (inquiry_id,))
                    # Skip first result set (starting balance?)
                    cursor.nextset()
                    hours_data = cursor.fetchall()
                    hours_dict = {}
                    if hours_data:
                        hours_columns = [desc[0] for desc in cursor.description]
                        hours_dict = dict(zip(hours_columns, hours_data[0]))
                    # Next result set
                    cursor.nextset()
                    name_data = cursor.fetchall()
                    name_dict = {}
                    if name_data:
                        name_columns = [desc[0] for desc in cursor.description]
                        name_dict = dict(zip(name_columns, name_data[0]))
                    consolidated = {**hours_dict, **name_dict}
                    consolidated["InquiryID"] = inquiry_id
                    return consolidated
                finally:
                    cursor.close()
                    try:
                        pyodbc_conn.commit()
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(
                f"Error processing inquiry {inquiry_id} (attempt {attempt + 1}/{max_retries}): {e}"
            )
            if attempt < max_retries - 1:
                time.sleep(1 + attempt)
            else:
                logger.error(f"Final error processing inquiry {inquiry_id}: {e}")
                return None


def _process_inquiry_batch(inquiry_batch: List[int]) -> List[Dict]:
    results: List[Dict] = []
    for inquiry_id in inquiry_batch:
        logger.info(f"Processing inquiry {inquiry_id}...")
        result = _sproc_account_balance(inquiry_id)
        if result is not None:
            results.append(result)
        time.sleep(0.1)
    return results


def aggregate_account_balance(
    franchise_id: int,
    batch_size: int = 1000,
    max_workers: int = 3,
) -> pd.DataFrame:
    logger.info(f"Starting processing for franchise {franchise_id}")
    inquiry_ids = get_inquiry_list(franchise_id)
    total = len(inquiry_ids)
    logger.info(f"Found {total} inquiries.")
    if not inquiry_ids:
        return pd.DataFrame()

    batches = [inquiry_ids[i : i + batch_size] for i in range(0, total, batch_size)]
    consolidated: List[Dict] = []
    processed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_process_inquiry_batch, b): b for b in batches}
        for fut in as_completed(futures):
            batch = futures[fut]
            try:
                batch_results = fut.result()
                consolidated.extend(batch_results)
                processed += len(batch)
                logger.info(f"Completed batch. Progress: {processed}/{total}")
            except Exception as e:
                logger.error(f"Batch processing failed: {e}")
    return pd.DataFrame(consolidated) if consolidated else pd.DataFrame()

