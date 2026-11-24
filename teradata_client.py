import logging
import re
from typing import Any, Dict, Generator, List, Optional, Tuple

import teradatasql


logger = logging.getLogger(__name__)


class TeradataClient:
    """
    A client to interact with Teradata database.
    """

    def __init__(self, host: str, user: str, password: str) -> None:
        """
        Initialize a TeradataClient instance.

        :param str host: The hostname or COP address of the Teradata server.
        :param str user: The username used for authentication.
        :param str password: The password associated with the username.
        """

        self.host = host
        self.user = user
        self.password = password
        self._teradata_session: teradatasql.TeradataConnection = None

    def __enter__(self) -> "TeradataClient":
        """
        Context manager entry. Create Teradata session lazily.

        :return: The ``TeradataClient`` instance itself for use in ``with`` statement.
        :rtype: TeradataClient
        """
        _ = self.session
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Context manager exit. Closes the Teradata session.

        :param exc_type: Exception type if an exception occurred.
        :param exc_val: Exception value if an exception occurred.
        :param exc_tb: Exception traceback if an exception occurred.
        :return: ``None``.
        :rtype: None
        """
        self._close_session()

    def __del__(self) -> None:
        """
        Destructor. Ensures the Teradata session is closed
        """
        self._close_session()

    @property
    def session(self) -> teradatasql.TeradataConnection:
        """
        Return the active Teradata session, creating one if necessary.

        Establishes a connection to the Teradata database on first access.
        Subsequent calls return the same cached session.

        :return: The active Teradata session object.
        :rtype: teradatasql.TeradataConnection
        :raises Exception: If an error occurs during connection establishment.
        """
        if not self._teradata_session:
            try:
                self._teradata_session = teradatasql.connect(
                    host=self.host, user=self.user, password=self.password
                )
                logger.info("Connection to Terradata successful")
            except Exception as e:
                logger.error(f"Error connecting to Teradata: {e}")
                raise
        return self._teradata_session

    def _close_session(self) -> None:
        """
        Close the active Teradata session if it exists.
        """
        if self._teradata_session:
            logger.debug("Closing Teradata session...")
            self._teradata_session.close()
            self._teradata_session = None
            logger.debug("Teradata session successfully closed.")

    def _mask_secrets(self, sql: str) -> str:
        """
        Mask sensitive information in SQL queries for secure logging.

        This method replaces strings with placeholder text to prevent
        credential exposure in logs.

        :param str sql: The SQL query string to mask.
        :return: The SQL query with sensitive values replaced with ``"********"``.
        :rtype: str
        """
        masked = sql
        secret_fields = ["PASSWORD"]

        # Mask known secret fields
        for field in secret_fields:
            masked = re.sub(
                rf'{field}\s*=\s*["\'][^"\']*["\']',
                f'{field} = "********"',
                masked,
                flags=re.IGNORECASE,
            )

        # Mask generic long random strings (fallback)
        masked = re.sub(r'=["\'][A-Za-z0-9+/=_-]{12,}["\']', '="********"', masked)

        return masked

    def _result_generator(
        self, cursor: teradatasql.TeradataCursor, fetch_size: int
    ) -> Generator[List[Tuple[Any, ...]], None, None]:
        """
        Generate batches of rows from a Teradata SQL cursor using ``fetchmany()``.

        :param teradatasql.TeradataCursor cursor: The Teradata cursor used to fetch results.
        :param int fetch_size: The number of rows to fetch per batch.
        :return: A generator yielding lists of tuples, each representing a batch of fetched rows.
        :rtype: Generator[List[Tuple[Any, ...]], None, None]
        :raises Exception: If an error occurs while fetching data from the cursor.
        """
        try:
            while True:
                batch = cursor.fetchmany(fetch_size)
                if not batch:
                    break
                yield batch
        except Exception as e:
            logger.error(
                f"An error occurred while fetching data from the Teradata cursor: {e}"
            )
            raise
        finally:
            cursor.close()

    def execute_query(
        self, query: str, message: str, fetch_size: Optional[int] = None
    ) -> Optional[Tuple[List[str], Generator[List[Tuple[Any, ...]], None, None]]]:
        """
        Execute a SQL query on the Teradata database.

        :param query: The SQL query to execute.
        :type query: str
        :param fetch_size: The number of rows to fetch if results are returned.
        :type fetch_size: Optional[int]
        :return: A tuple containing the list of column names and a generator yielding batches of result rows,
                or None if the query returns no result seteildiievatatceeultsoor        :rtype: Optional[Tuple[List[str], Generator[List[Tuple[Any, ...]], None, None]]]
        :raises Exception: If there is an error executing the query.
        """
        logger.info(f"{message}")
        try:
            cursor = self.session.cursor()
            safe_query = self._mask_secrets(query)
            logger.info(f"Executing SQL query: \n{safe_query}")
            cursor.execute(query)
            logger.info(f"Query to {message} was successfully executed.")

            if cursor.description:  # i.e. if sql query return results
                columns = [desc[0] for desc in cursor.description]
                return columns, self._result_generator(
                    cursor=cursor, fetch_size=fetch_size
                )
            else:
                cursor.close()

        except Exception as e:
            logger.error(f"Error executing query: {e}")
            raise

    def fetch(
        self, query: str, message: str, fetch_size: Optional[int] = None
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Execute a SQL query and yield each result row as a dictionary.

        Combines the column names with each row tuple to produce dictionaries
        that map column names to their values.

        :param str query: The SQL query to execute.
        :param str message: A descriptive message for logging purposes.
        :param Optional[int] fetch_size: The number of rows to fetch per batch. Defaults to ``None``.
        :return: Generator yielding each row as a dictionary mapping column names to values.
        :rtype: Generator[Dict[str, Any], None, None]
        :raises Exception: If an error occurs while executing the query.
        """
        result = self.execute_query(query, message, fetch_size)
        if result:
            columns, batches = result
            for batch in batches:
                for row in batch:
                    yield dict(zip(columns, row))

    def execute_multi_statement(
        self, query: str, message: str, delimiter: str = "-----"
    ) -> None:
        """
        Execute multiple SQL statements on the Teradata database.

        Since Teradata does not allow multiple DDL statements in a single ``execute()`` call,
        this method splits the script into individual statements and executes each separately.

        :param str query: The SQL script containing one or more SQL statements separated by the delimiter.
        :param str message: A descriptive message for logging purposes.
        :param str delimiter: The delimiter string used to split SQL statements. Defaults to ``"-----"``.
        :return: ``None``.
        :rtype: None
        :raises Exception: If an error occurs while executing any statement.
        """

        logger.info(f"{message}")

        try:
            cursor = self.session.cursor()

            # Split SQL script into individual statements
            statements = [
                stmt.strip() for stmt in query.split(delimiter) if stmt.strip()
            ]

            for stmt in statements:
                logger.info(f"Executing SQL statement: {stmt}")

                try:
                    cursor.execute(stmt)

                    # DDL returns no result set, but we mimic execute_query() behavior
                    if cursor.description:
                        logger.warning(
                            "Unexpected result set returned for a DDL statement."
                        )

                except Exception as e:
                    logger.error(f"Error executing statement: {stmt}\n{e}")
                    raise

            cursor.close()

        except Exception as e:
            logger.error(f"Error executing multi-statement SQL script: {e}")
            raise
