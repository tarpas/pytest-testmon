"""Import dependencies: project modules a file imports, found statically.

A test that only reads a constant, a class attribute or a generated method
(dataclass, NamedTuple) of a module executes no line there, so coverage does not
record the module. The import statements of the files the test did execute tell
us about such modules; the test then depends on their module-level code.

Import statements are read from the source (ast). Names are resolved through
sys.modules, so a module counts only if it was really imported in this process.
`from package import name` is followed through re-exports to the module that
defines `name`, instead of depending on everything the package imports.
"""

import ast
import os
import sys
from importlib.util import resolve_name
from pathlib import Path

from testmon.process_code import read_source_sha

STAR = "*"


def parse_imports(source_code):
    """Return (imports, exports) for the import statements in source_code.

    imports is a list of (module, level, name): `import a.b` gives
    ("a.b", 0, None); `from .m import x as y` gives ("m", 1, "x");
    `from m import *` gives ("m", 0, STAR).
    exports maps a name bound by `from ... import` to its record, and STAR to
    the list of star imports.
    """
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return [], {}
    imports = []
    # What a name bound at module level stands for; used to follow re-exports.
    exports = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, 0, None))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                record = (node.module or "", node.level, alias.name)
                imports.append(record)
                if alias.name == STAR:
                    exports.setdefault(STAR, []).append(record)
                else:
                    exports[alias.asname or alias.name] = record
    return imports, exports


class ImportGraph:
    """Resolves the import dependencies of project files.

    Has to live in the process that ran the tests (under xdist: the worker),
    because only its sys.modules knows the imported modules.
    """

    def __init__(self, rootdir):
        self.rootdir = os.path.realpath(rootdir)
        self._parsed = {}
        self._names = None
        self._files = None
        self._dependencies = {}

    def refresh(self):
        """Forget what was resolved through sys.modules; it grows during a run."""
        self._names = None
        self._files = None
        self._dependencies = {}

    def _index_modules(self):
        self._names = {}
        self._files = {}
        for name, module in list(sys.modules.items()):
            filename = getattr(module, "__file__", None)
            if not filename or not filename.endswith(".py"):
                continue
            path = os.path.realpath(filename)
            if not path.startswith(self.rootdir + os.sep):
                continue
            relpath = os.path.relpath(path, self.rootdir).replace(os.sep, "/")
            self._files[name] = relpath
            if hasattr(module, "__path__"):
                package = name
            else:
                package = name.rpartition(".")[0]
            # A file can be imported under several names; any of them resolves
            # its relative imports the same way.
            self._names.setdefault(relpath, package)

    def _parse(self, filename):
        if filename not in self._parsed:
            source_code = read_source_sha(Path(self.rootdir) / filename)[0]
            self._parsed[filename] = parse_imports(source_code or "")
        return self._parsed[filename]

    def _absolute(self, module, level, package):
        if not level:
            return module
        try:
            return resolve_name("." * level + module, package)
        except (ImportError, ValueError):
            return None

    def _follow(self, record, package, found, seen):
        """Add the files which `record`, imported from `package`, depends on."""
        module, level, name = record
        target = self._absolute(module, level, package)
        if not target:
            return
        if name and name != STAR and f"{target}.{name}" in self._files:
            # from package import submodule
            found.add(self._files[f"{target}.{name}"])
            return
        filename = self._files.get(target)
        if not filename or (filename, name) in seen:
            return
        seen.add((filename, name))
        found.add(filename)
        if not name:
            return
        # The name may be re-exported: defined in another module and imported here.
        exports = self._parse(filename)[1]
        target_package = self._names.get(filename, "")
        if name != STAR and name in exports:
            self._follow(exports[name], target_package, found, seen)
        else:
            for star_record in exports.get(STAR, []):
                self._follow(
                    (star_record[0], star_record[1], name), target_package, found, seen
                )

    def dependencies(self, filename):
        """Project files that `filename` imports, as paths relative to rootdir."""
        if self._names is None:
            self._index_modules()
        if filename not in self._dependencies:
            found = set()
            if filename.endswith(".py") and filename in self._names:
                package = self._names[filename]
                for record in self._parse(filename)[0]:
                    self._follow(record, package, found, set())
            found.discard(filename)
            self._dependencies[filename] = found
        return self._dependencies[filename]

    def nodes_imports(self, nodes_files_lines):
        """For each test: the files imported by the files it executed, in which
        it executed nothing itself."""
        self.refresh()
        result = {}
        for test_name, covered_files in nodes_files_lines.items():
            imported = set()
            for filename in covered_files:
                imported.update(self.dependencies(filename))
            imported.difference_update(covered_files)
            if imported:
                result[test_name] = sorted(imported)
        return result
