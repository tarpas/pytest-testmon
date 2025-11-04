#!/usr/bin/env python3
"""
analyze.py
Testmon Database Analyzer
Displays pytest-ezmon data in a human-readable format
"""

import sqlite3
import sys
from pathlib import Path
from array import array
from collections import defaultdict
from typing import List, Dict, Tuple
import argparse


def blob_to_checksums(blob: bytes) -> List[int]:
    """Convert binary blob to list of checksums (signed integers)"""
    if not blob:
        return []
    arr = array('i')  # signed int
    arr.frombytes(blob)
    return arr.tolist()


def format_checksum(checksum: int) -> str:
    """Format checksum for display"""
    return f"{checksum:010d}" if checksum >= 0 else f"{checksum:011d}"


def format_duration(seconds: float) -> str:
    """Format duration in human-readable form"""
    if seconds < 0.001:
        return f"{seconds * 1000000:.1f}µs"
    elif seconds < 1:
        return f"{seconds * 1000:.2f}ms"
    else:
        return f"{seconds:.3f}s"


class TestmonAnalyzer:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.conn.close()

    def get_environment_info(self) -> Dict:
        """Get environment information"""
        cursor = self.conn.execute(
            "SELECT * FROM environment"
        )
        row = cursor.fetchone()
        if row:
            return dict(row)
        return {}

    def get_metadata(self) -> Dict:
        """Get metadata statistics"""
        cursor = self.conn.execute("SELECT * FROM metadata")
        metadata = {}
        for row in cursor:
            metadata[row['dataid']] = row['data']
        return metadata

    def get_all_tests(self) -> List[Dict]:
        """Get all test executions with their details"""
        cursor = self.conn.execute("""
            SELECT 
                te.id,
                te.test_name,
                te.duration,
                te.failed,
                te.forced
            FROM test_execution te
            ORDER BY te.test_name
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_test_dependencies(self, test_id: int) -> List[Dict]:
        """Get file dependencies for a specific test"""
        cursor = self.conn.execute("""
            SELECT 
                fp.filename,
                fp.fsha,
                fp.method_checksums,
                fp.mtime
            FROM test_execution_file_fp tef
            JOIN file_fp fp ON tef.fingerprint_id = fp.id
            WHERE tef.test_execution_id = ?
            ORDER BY fp.filename
        """, (test_id,))

        deps = []
        for row in cursor:
            dep = dict(row)
            dep['checksums'] = blob_to_checksums(row['method_checksums'])
            deps.append(dep)
        return deps

    def get_file_fingerprints(self) -> List[Dict]:
        """Get all file fingerprints"""
        cursor = self.conn.execute("""
            SELECT 
                id,
                filename,
                fsha,
                method_checksums,
                mtime
            FROM file_fp
            ORDER BY filename, id
        """)

        fps = []
        for row in cursor:
            fp = dict(row)
            fp['checksums'] = blob_to_checksums(row['method_checksums'])
            fps.append(fp)
        return fps

    def get_test_file_map(self) -> Dict[str, List[str]]:
        """Map tests to files they depend on"""
        cursor = self.conn.execute("""
            SELECT 
                te.test_name,
                fp.filename
            FROM test_execution te
            JOIN test_execution_file_fp tef ON te.id = tef.test_execution_id
            JOIN file_fp fp ON tef.fingerprint_id = fp.id
            ORDER BY te.test_name, fp.filename
        """)

        test_files = defaultdict(set)
        for row in cursor:
            test_files[row['test_name']].add(row['filename'])

        return {test: sorted(files) for test, files in test_files.items()}

    def get_file_test_map(self) -> Dict[str, List[str]]:
        """Map files to tests that depend on them"""
        cursor = self.conn.execute("""
            SELECT DISTINCT
                fp.filename,
                te.test_name
            FROM file_fp fp
            JOIN test_execution_file_fp tef ON fp.id = tef.fingerprint_id
            JOIN test_execution te ON tef.test_execution_id = te.id
            ORDER BY fp.filename, te.test_name
        """)

        file_tests = defaultdict(set)
        for row in cursor:
            file_tests[row['filename']].add(row['test_name'])

        return {file: sorted(tests) for file, tests in file_tests.items()}

    def print_summary(self):
        """Print summary statistics"""
        print("=" * 80)
        print("TESTMON DATABASE ANALYSIS")
        print("=" * 80)
        print(f"\nDatabase: {self.db_path}")
        print()

        # Environment info
        env = self.get_environment_info()
        if env:
            print("Environment:")
            print(f"  Name: {env['environment_name']}")
            print(f"  Python: {env['python_version']}")
            packages = env['system_packages']
            if len(packages) > 80:
                print(f"  Packages: {packages[:80]}...")
            else:
                print(f"  Packages: {packages}")
            print()

        # Metadata
        metadata = self.get_metadata()
        if metadata:
            print("Overall Statistics:")
            time_saved = float(metadata.get('None:time_saved', 0))
            time_all = float(metadata.get('None:time_all', 0))
            tests_saved = int(metadata.get('None:tests_saved', 0))
            tests_all = int(metadata.get('None:tests_all', 0))

            print(f"  Total test runs: {tests_all}")
            if tests_all > 0:
                print(f"  Tests skipped: {tests_saved} ({100 * tests_saved / tests_all:.1f}%)")
            else:
                print(f"  Tests skipped: 0")
            print(f"  Time saved: {format_duration(time_saved)} / {format_duration(time_all)}")
            if time_all > 0:
                print(f"  Efficiency: {100 * time_saved / time_all:.1f}% time saved")
            print()

        # Test counts
        tests = self.get_all_tests()
        print(f"Total Tests Tracked: {len(tests)}")
        failed = sum(1 for t in tests if t['failed'])
        if failed:
            print(f"  Failed: {failed}")
            print(f"  Passed: {len(tests) - failed}")
        else:
            print(f"  All tests passed!")
        print()

        # File counts
        cursor = self.conn.execute("SELECT COUNT(DISTINCT filename) FROM file_fp")
        file_count = cursor.fetchone()[0]
        print(f"Files Tracked: {file_count}")

        cursor = self.conn.execute("SELECT COUNT(*) FROM file_fp")
        fp_count = cursor.fetchone()[0]
        print(f"File Fingerprints: {fp_count}")
        print()

    def print_tests_detail(self):
        """Print detailed test information"""
        print("=" * 80)
        print("TEST DETAILS")
        print("=" * 80)
        print()

        tests = self.get_all_tests()

        for test in tests:
            status = "✗ FAILED" if test['failed'] else "✓ PASSED"
            forced = " [FORCED]" if test.get('forced') else ""
            print(f"{status}{forced}: {test['test_name']}")
            print(f"  Duration: {format_duration(test['duration'])}")

            deps = self.get_test_dependencies(test['id'])
            if deps:
                print(f"  Dependencies ({len(deps)} file fingerprint(s)):")
                for dep in deps:
                    print(f"    📄 {dep['filename']}")
                    print(f"       SHA: {dep['fsha'][:16]}...")
                    checksums = dep['checksums']
                    if len(checksums) <= 5:
                        checksum_str = ', '.join(format_checksum(c) for c in checksums)
                    else:
                        checksum_str = ', '.join(format_checksum(c) for c in checksums[:3])
                        checksum_str += f", ... ({len(checksums)} blocks total)"
                    print(f"       Blocks: [{checksum_str}]")
            print()

    def print_file_dependencies(self):
        """Print file dependency information"""
        print("=" * 80)
        print("FILE DEPENDENCIES")
        print("=" * 80)
        print()

        file_tests = self.get_file_test_map()

        for filename in sorted(file_tests.keys()):
            tests = file_tests[filename]
            print(f"📄 {filename}")
            print(f"   Used by {len(tests)} test(s):")
            for test in tests:
                print(f"     • {test}")
            print()

    def print_test_coverage_matrix(self):
        """Print a matrix showing which tests cover which files"""
        print("=" * 80)
        print("TEST-FILE COVERAGE MATRIX")
        print("=" * 80)
        print()

        test_files = self.get_test_file_map()
        all_files = set()
        for files in test_files.values():
            all_files.update(files)

        all_files = sorted(all_files)
        tests = sorted(test_files.keys())

        # Print header
        print(f"{'Test':<50} | Files")
        print("-" * 80)

        for test in tests:
            files = test_files[test]
            print(f"{test:<50} | {', '.join(files)}")
        print()

    def print_file_fingerprints(self):
        """Print all file fingerprints"""
        print("=" * 80)
        print("FILE FINGERPRINTS (Detailed)")
        print("=" * 80)
        print()
        print("This shows all stored fingerprints for each file.")
        print("Multiple fingerprints = file changed over time or different code paths tracked.")
        print()

        fps = self.get_file_fingerprints()
        current_file = None

        for fp in fps:
            if fp['filename'] != current_file:
                if current_file:
                    print()
                current_file = fp['filename']
                print(f"📄 {fp['filename']}")

            print(f"   Fingerprint #{fp['id']}")
            print(f"     SHA: {fp['fsha']}")
            checksums = fp['checksums']
            print(f"     Blocks: {len(checksums)}")
            if checksums:
                if len(checksums) <= 10:
                    for i, cs in enumerate(checksums, 1):
                        print(f"       {i}. {format_checksum(cs)}")
                else:
                    for i, cs in enumerate(checksums[:5], 1):
                        print(f"       {i}. {format_checksum(cs)}")
                    print(f"       ... ({len(checksums) - 5} more blocks)")
        print()

    def print_slowest_tests(self, n: int = 10):
        """Print the N slowest tests"""
        print("=" * 80)
        print(f"TOP {n} SLOWEST TESTS")
        print("=" * 80)
        print()

        tests = self.get_all_tests()
        tests.sort(key=lambda t: t['duration'], reverse=True)

        for i, test in enumerate(tests[:min(n, len(tests))], 1):
            status = "✗" if test['failed'] else "✓"
            print(f"{i:2d}. {status} {test['test_name']}")
            print(f"    {format_duration(test['duration'])}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='Analyze pytest-ezmon database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use default path, show standard sections
  %(prog)s --db /path/to/.testmondata        # Specify database path
  %(prog)s --section tests                   # Show only test details
  %(prog)s --section files                   # Show only file dependencies
  %(prog)s --all                             # Show all sections including verbose ones
        """
    )

    parser.add_argument(
        '--db',
        default='/Users/andrew_yos/testmon-test/.testmondata',
        help='Path to .testmondata file (default: /Users/andrew_yos/ezmon-test/.testmondata)'
    )

    parser.add_argument(
        '--section',
        choices=['summary', 'tests', 'files', 'matrix', 'slowest', 'fingerprints'],
        help='Show only specific section'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Show all sections including verbose ones (fingerprints)'
    )

    parser.add_argument(
        '--top',
        type=int,
        default=10,
        help='Number of slowest tests to show (default: 10)'
    )

    args = parser.parse_args()

    # Check if database exists
    if not Path(args.db).exists():
        print(f"Error: Database file not found: {args.db}", file=sys.stderr)
        print("\nUse --db to specify the correct path to .testmondata", file=sys.stderr)
        sys.exit(1)

    # Determine which sections to show
    if args.section:
        sections = {args.section}
    elif args.all:
        sections = {'summary', 'tests', 'files', 'matrix', 'slowest', 'fingerprints'}
    else:
        # Default sections (exclude fingerprints as it's verbose)
        sections = {'summary', 'tests', 'files', 'matrix', 'slowest'}

    # Analyze database
    with TestmonAnalyzer(args.db) as analyzer:
        if 'summary' in sections:
            analyzer.print_summary()

        if 'tests' in sections:
            analyzer.print_tests_detail()

        if 'files' in sections:
            analyzer.print_file_dependencies()

        if 'matrix' in sections:
            analyzer.print_test_coverage_matrix()

        if 'slowest' in sections:
            analyzer.print_slowest_tests(args.top)

        if 'fingerprints' in sections:
            analyzer.print_file_fingerprints()


if __name__ == '__main__':
    main()