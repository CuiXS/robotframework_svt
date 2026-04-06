#!/usr/bin/env python

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

"""Command-line tool for parsing Robot Framework output files and storing
results in a SQLite database.

Usage::

    reportparser output.xml [output2.xml ...] [--db results.db]

Options:
    output          One or more Robot Framework output XML (or JSON) files
                    to parse.
    --db PATH       Path to the SQLite database file.  Defaults to
                    ``results.db`` in the current directory.  The file is
                    created if it does not exist.  Existing data is kept so
                    that multiple runs can be stored in the same database.
    -h, --help      Show this help text.
"""

import sys
from pathlib import Path


def _parse_args(args):
    db_path = 'results.db'
    outputs = []
    it = iter(args)
    for arg in it:
        if arg in ('-h', '--help'):
            print(__doc__)
            sys.exit(0)
        elif arg == '--db':
            try:
                db_path = next(it)
            except StopIteration:
                _error("--db requires a path argument")
        elif arg.startswith('--db='):
            db_path = arg[5:]
        else:
            outputs.append(arg)
    if not outputs:
        _error("At least one output file is required.")
    return outputs, db_path


def _error(msg):
    print(f"Error: {msg}", file=sys.stderr)
    print("Use --help for usage information.", file=sys.stderr)
    sys.exit(1)


def main(args=None):
    """Entry point for the ``reportparser`` command."""
    if args is None:
        args = sys.argv[1:]
    outputs, db_path = _parse_args(args)

    # Deferred import so the module can be imported without robot on the path.
    from robot.api import ExecutionResult
    from robot.result.dbexporter import ResultToDbExporter

    with ResultToDbExporter(db_path) as exporter:
        for output in outputs:
            path = Path(output)
            if not path.exists():
                _error(f"File not found: {output}")
            result = ExecutionResult(path)
            run_id = exporter.export(result)
            total = result.suite.statistics
            print(
                f"[run {run_id}] {output}: "
                f"{total.passed} passed, "
                f"{total.failed} failed, "
                f"{total.skipped} skipped  →  {db_path}"
            )


def reportparser_cli():
    """Entry point registered in setup.py."""
    main()


if __name__ == '__main__':
    main()
