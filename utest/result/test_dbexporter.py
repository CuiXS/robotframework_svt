import os
import sqlite3
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from robot.api import ExecutionResult
from robot.result.dbexporter import ResultToDbExporter


CURDIR = Path(__file__).resolve().parent

# Minimal XML output with one passing and one failing test case.
SIMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 7.0 (Python 3.12 on linux)" generated="2024-01-15T10:00:00.000000" rpa="false" schemaversion="5">
<suite id="s1" name="My Suite" source="test.robot">
  <test id="s1-t1" name="Passing Test">
    <tag>smoke</tag>
    <tag>fast</tag>
    <doc>A passing test</doc>
    <status status="PASS" start="2024-01-15T10:00:01.000000" elapsed="0.100000"/>
  </test>
  <test id="s1-t2" name="Failing Test">
    <doc>A failing test</doc>
    <status status="FAIL" start="2024-01-15T10:00:02.000000" elapsed="0.050000">AssertionError: Expected True</status>
  </test>
  <status status="FAIL" start="2024-01-15T10:00:00.900000" elapsed="0.300000"/>
</suite>
<statistics>
  <total><stat pass="1" fail="1" skip="0">All Tests</stat></total>
  <tag>
    <stat pass="1" fail="0" skip="0">fast</stat>
    <stat pass="1" fail="0" skip="0">smoke</stat>
  </tag>
  <suite><stat name="My Suite" id="s1" pass="1" fail="1" skip="0">My Suite</stat></suite>
</statistics>
<errors/>
</robot>
"""

# XML with nested suites.
NESTED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<robot generator="Robot 7.0 (Python 3.12 on linux)" generated="2024-01-16T09:00:00.000000" rpa="false" schemaversion="5">
<suite id="s1" name="Root">
  <suite id="s1-s1" name="Child">
    <test id="s1-s1-t1" name="Nested Test">
      <status status="PASS" start="2024-01-16T09:00:01.000000" elapsed="0.010000"/>
    </test>
    <status status="PASS" start="2024-01-16T09:00:00.500000" elapsed="0.100000"/>
  </suite>
  <status status="PASS" start="2024-01-16T09:00:00.000000" elapsed="0.200000"/>
</suite>
<statistics>
  <total><stat pass="1" fail="0" skip="0">All Tests</stat></total>
  <tag/>
  <suite>
    <stat name="Root" id="s1" pass="1" fail="0" skip="0">Root</stat>
    <stat name="Root.Child" id="s1-s1" pass="1" fail="0" skip="0">Root.Child</stat>
  </suite>
</statistics>
<errors/>
</robot>
"""


class TestResultToDbExporterBasic(unittest.TestCase):

    def setUp(self):
        fd, self._tmp = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.result = ExecutionResult(StringIO(SIMPLE_XML))
        self.exporter = ResultToDbExporter(self._tmp)

    def tearDown(self):
        self.exporter.close()
        if os.path.exists(self._tmp):
            os.remove(self._tmp)

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def test_tables_are_created(self):
        conn = sqlite3.connect(self._tmp)
        tables = {row[0] for row in
                  conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        self.assertIn('test_runs', tables)
        self.assertIn('test_suites', tables)
        self.assertIn('test_cases', tables)

    # ------------------------------------------------------------------
    # test_runs table
    # ------------------------------------------------------------------

    def test_run_is_inserted(self):
        run_id = self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        row = conn.execute("SELECT * FROM test_runs WHERE id=?", (run_id,)).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        _id, source, generator, generated = row
        self.assertEqual(generator, 'Robot 7.0 (Python 3.12 on linux)')
        self.assertEqual(generated, '2024-01-15T10:00:00')

    def test_run_returns_correct_id(self):
        id1 = self.exporter.export(self.result)
        id2 = self.exporter.export(self.result)
        self.assertNotEqual(id1, id2)
        self.assertGreater(id2, id1)

    # ------------------------------------------------------------------
    # test_suites table
    # ------------------------------------------------------------------

    def test_suite_is_inserted(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        rows = conn.execute("SELECT name, longname, status FROM test_suites").fetchall()
        conn.close()
        self.assertEqual(len(rows), 1)
        name, longname, status = rows[0]
        self.assertEqual(name, 'My Suite')
        self.assertEqual(longname, 'My Suite')
        self.assertEqual(status, 'FAIL')

    # ------------------------------------------------------------------
    # test_cases table
    # ------------------------------------------------------------------

    def test_tests_are_inserted(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        rows = conn.execute(
            "SELECT name, status, message FROM test_cases ORDER BY id"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], 'Passing Test')
        self.assertEqual(rows[0][1], 'PASS')
        self.assertEqual(rows[1][0], 'Failing Test')
        self.assertEqual(rows[1][1], 'FAIL')
        self.assertIn('AssertionError', rows[1][2])

    def test_tags_are_stored_as_comma_separated(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        row = conn.execute(
            "SELECT tags FROM test_cases WHERE name='Passing Test'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        tags = {t.strip() for t in row[0].split(',')}
        self.assertIn('smoke', tags)
        self.assertIn('fast', tags)

    def test_test_without_tags_has_empty_tags(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        row = conn.execute(
            "SELECT tags FROM test_cases WHERE name='Failing Test'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], '')

    def test_run_id_foreign_key(self):
        run_id = self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        rows = conn.execute(
            "SELECT run_id FROM test_cases"
        ).fetchall()
        conn.close()
        for (rid,) in rows:
            self.assertEqual(rid, run_id)

    def test_suite_id_foreign_key(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        suite_ids = {row[0] for row in
                     conn.execute("SELECT id FROM test_suites").fetchall()}
        tc_suite_ids = {row[0] for row in
                        conn.execute("SELECT suite_id FROM test_cases").fetchall()}
        conn.close()
        self.assertTrue(tc_suite_ids.issubset(suite_ids))


class TestResultToDbExporterNested(unittest.TestCase):

    def setUp(self):
        fd, self._tmp = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        self.result = ExecutionResult(StringIO(NESTED_XML))
        self.exporter = ResultToDbExporter(self._tmp)

    def tearDown(self):
        self.exporter.close()
        if os.path.exists(self._tmp):
            os.remove(self._tmp)

    def test_nested_suites_are_inserted(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        rows = conn.execute(
            "SELECT name, parent_id FROM test_suites ORDER BY id"
        ).fetchall()
        conn.close()
        self.assertEqual(len(rows), 2)
        root_name, root_parent = rows[0]
        child_name, child_parent = rows[1]
        self.assertEqual(root_name, 'Root')
        self.assertIsNone(root_parent)
        self.assertEqual(child_name, 'Child')
        self.assertIsNotNone(child_parent)

    def test_nested_test_case_is_inserted(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        row = conn.execute(
            "SELECT name, longname, status FROM test_cases"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        name, longname, status = row
        self.assertEqual(name, 'Nested Test')
        self.assertEqual(longname, 'Root.Child.Nested Test')
        self.assertEqual(status, 'PASS')


class TestResultToDbExporterContextManager(unittest.TestCase):

    def test_context_manager_closes_connection(self):
        fd, tmp = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        try:
            result = ExecutionResult(StringIO(SIMPLE_XML))
            with ResultToDbExporter(tmp) as exporter:
                exporter.export(result)
            # After closing, accessing the internal connection should fail.
            with self.assertRaises(Exception):
                exporter._conn.execute("SELECT 1")
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)


class TestResultToDbExporterFromFile(unittest.TestCase):
    """Integration test using the golden.xml fixture."""

    def setUp(self):
        fd, self._tmp = tempfile.mkstemp(suffix='.db')
        os.close(fd)
        golden = CURDIR / 'golden.xml'
        self.result = ExecutionResult(golden)
        self.exporter = ResultToDbExporter(self._tmp)

    def tearDown(self):
        self.exporter.close()
        if os.path.exists(self._tmp):
            os.remove(self._tmp)

    def test_golden_test_is_stored(self):
        self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        row = conn.execute(
            "SELECT name, status FROM test_cases WHERE name='First One'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 'PASS')

    def test_generator_is_stored(self):
        run_id = self.exporter.export(self.result)
        conn = sqlite3.connect(self._tmp)
        row = conn.execute(
            "SELECT generator FROM test_runs WHERE id=?", (run_id,)
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertIn('Rebot', row[0])


if __name__ == '__main__':
    unittest.main()
