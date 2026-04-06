#  Copyright 2008-2015 Nokia Networks
#  Copyright 2016-     Robot Framework Foundation
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

"""Export Robot Framework execution results to a SQLite database.

Usage example::

    from robot.api import ExecutionResult
    from robot.result.dbexporter import ResultToDbExporter

    result = ExecutionResult('output.xml')
    exporter = ResultToDbExporter('results.db')
    exporter.export(result)
    exporter.close()

The database contains the following tables:

* ``test_runs`` — one row per parsed output file with version/generator info.
* ``test_suites`` — one row per suite (nested suites included).
* ``test_cases`` — one row per test case with status, message, tags, etc.
"""

import sqlite3
from pathlib import Path

from .visitor import ResultVisitor


_DDL = """
CREATE TABLE IF NOT EXISTS test_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT,
    generator   TEXT,
    generated   TEXT
);

CREATE TABLE IF NOT EXISTS test_suites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES test_runs(id),
    parent_id   INTEGER REFERENCES test_suites(id),
    name        TEXT,
    longname    TEXT,
    doc         TEXT,
    status      TEXT,
    start_time  TEXT,
    end_time    TEXT,
    elapsed_ms  REAL
);

CREATE TABLE IF NOT EXISTS test_cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      INTEGER NOT NULL REFERENCES test_runs(id),
    suite_id    INTEGER NOT NULL REFERENCES test_suites(id),
    name        TEXT,
    longname    TEXT,
    doc         TEXT,
    status      TEXT,
    message     TEXT,
    start_time  TEXT,
    end_time    TEXT,
    elapsed_ms  REAL,
    tags        TEXT
);
"""


class ResultToDbExporter:
    """Export a :class:`~robot.result.executionresult.Result` to a SQLite database.

    :param db_path: Path to the SQLite database file.  It will be created
        if it does not already exist.
    """

    def __init__(self, db_path: 'str|Path'):
        self._db_path = Path(db_path)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.executescript(_DDL)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def export(self, result) -> int:
        """Export *result* to the database.

        :param result: A :class:`~robot.result.executionresult.Result` object.
        :returns: The ``id`` of the newly created ``test_runs`` row.
        """
        visitor = _ExportVisitor(self._conn)
        result.visit(visitor)
        return visitor.run_id

    def close(self):
        """Close the underlying database connection."""
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ------------------------------------------------------------------
# Internal visitor
# ------------------------------------------------------------------

class _ExportVisitor(ResultVisitor):
    """Collects data while visiting a Result and writes it to the database."""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self.run_id: int = -1
        self._suite_id_stack: 'list[int]' = []

    # Result

    def start_result(self, result):
        source = str(result.source) if result.source else None
        generated = (result.generation_time.isoformat()
                     if result.generation_time else None)
        cur = self._conn.execute(
            "INSERT INTO test_runs (source, generator, generated) VALUES (?, ?, ?)",
            (source, result.generator, generated)
        )
        self._conn.commit()
        self.run_id = cur.lastrowid

    # Suites

    def start_suite(self, suite):
        parent_id = self._suite_id_stack[-1] if self._suite_id_stack else None
        cur = self._conn.execute(
            """INSERT INTO test_suites
               (run_id, parent_id, name, longname, doc, status,
                start_time, end_time, elapsed_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.run_id, parent_id,
             suite.name, suite.longname, suite.doc,
             suite.status,
             suite.starttime, suite.endtime,
             suite.elapsedtime)
        )
        self._conn.commit()
        self._suite_id_stack.append(cur.lastrowid)

    def end_suite(self, suite):
        self._suite_id_stack.pop()

    # Tests

    def visit_test(self, test):
        suite_id = self._suite_id_stack[-1] if self._suite_id_stack else None
        tags = ', '.join(str(t) for t in test.tags)
        self._conn.execute(
            """INSERT INTO test_cases
               (run_id, suite_id, name, longname, doc, status, message,
                start_time, end_time, elapsed_ms, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.run_id, suite_id,
             test.name, test.longname, test.doc,
             test.status, test.message,
             test.starttime, test.endtime,
             test.elapsedtime,
             tags)
        )
        self._conn.commit()
