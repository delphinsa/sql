#!/usr/bin/env python3

import logging
import os
import sys
import time
from pathlib import Path

from teradata_client import TeradataClient


def execute_sql_file(client, sql_filename):
    sql_file = Path(__file__).with_name(sql_filename)
    query = sql_file.read_text(encoding="utf-8").strip()

    if not query:
        raise ValueError(f"Le fichier SQL est vide : {sql_file}")

    logging.info("Debut execution : %s", sql_filename)

    start_time = time.perf_counter()

    result = client.execute_query(
        query=query,
        message=f"Execution de {sql_filename}",
        fetch_size=1000,
    )

    elapsed = time.perf_counter() - start_time

    if result is None:
        logging.info(
            "%s termine en %.2f secondes",
            sql_filename,
            elapsed,
        )
    else:
        columns, batches = result
        row_count = sum(len(batch) for batch in batches)

        logging.info(
            "%s termine en %.2f secondes - Colonnes : %s ; lignes recuperees : %d",
            sql_filename,
            elapsed,
            columns,
            row_count,
        )

    return elapsed


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    host = "tdabdev.n18.an.cnav"
    user = "US_SYSDBA_DEV"
    password = "PW_SYSdbaTD_DEV23"

    with TeradataClient(host, user, password) as client:

        td_iceberg_time = execute_sql_file(
            client,
            "insert_into_tdIceberg_table.sql",
        )

        iceberg_time = execute_sql_file(
            client,
            "insert_into_Iceberg_table.sql",
        )

    total_time = td_iceberg_time + iceberg_time

    logging.info("")
    logging.info("===== RESUME DES INSERTS =====")
    logging.info(
        "insert_into_tdIceberg_table.sql : %.2f s",
        td_iceberg_time,
    )
    logging.info(
        "insert_into_Iceberg_table.sql   : %.2f s",
        iceberg_time,
    )
    logging.info(
        "Temps total                     : %.2f s",
        total_time,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.exception("Echec de l'execution des requetes.")
        sys.exit(1)