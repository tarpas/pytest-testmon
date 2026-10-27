import os
import time
import xml.etree.ElementTree as ET

from testmon.process_code import Module, INVERTED_GAP_MARKS_CHECKSUMS, get_source_sha


def get_file_coverage_from_checksums(rootdir, filename, covered_checksums):
    """Reconstruct line coverage from block checksums (fallback).

    Returns (covered_lines, all_block_lines) as sets of line numbers.
    """
    code, fsha = get_source_sha(directory=rootdir, filename=filename)
    if not fsha:
        return set(), set()
    mtime = os.path.getmtime(os.path.join(rootdir, filename))
    module = Module(
        source_code=code,
        mtime=mtime,
        ext=filename.rsplit(".", 1)[1] if "." in filename else "py",
        fs_fsha=fsha,
        filename=filename,
        rootdir=rootdir,
    )
    covered_lines = set()
    all_block_lines = set()

    gap_checksums = set(INVERTED_GAP_MARKS_CHECKSUMS.keys())

    for block, checksum in zip(module.blocks, module.checksums):
        if checksum in gap_checksums:
            continue
        lines_in_block = set(range(block.start, block.end + 1))
        all_block_lines |= lines_in_block
        if checksum in covered_checksums:
            covered_lines |= lines_in_block

    return covered_lines, all_block_lines


def _get_executable_lines(rootdir, filename):
    """Get the set of executable line numbers for a source file using coverage.py."""
    try:
        from coverage.python import PythonParser

        filepath = os.path.join(rootdir, filename)
        parser = PythonParser(filename=filepath)
        parser.parse_source()
        return set(parser.statements)
    except Exception:
        return None


def _infer_declaration_coverage(rootdir, filename, covered_lines, all_lines):
    """Mark def/class/import declaration lines as covered when their body is covered.

    coverage.py in context mode doesn't attribute declaration lines (class Foo:,
    def bar():, import x) to any test context. If the body of a function/class
    has covered lines, its declaration must have been executed too.
    """
    import ast

    filepath = os.path.join(rootdir, filename)
    try:
        with open(filepath) as f:
            source = f.read()
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return covered_lines

    result = covered_lines.copy()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            decl_line = node.lineno
            if decl_line not in all_lines:
                continue
            body_lines = set()
            for child in ast.walk(node):
                if hasattr(child, "lineno") and child is not node:
                    body_lines.add(child.lineno)
            if body_lines & covered_lines:
                result.add(decl_line)
                for decorator in node.decorator_list:
                    if hasattr(decorator, "lineno"):
                        result.add(decorator.lineno)

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if hasattr(node, "lineno") and node.lineno in all_lines:
                result.add(node.lineno)

    return result


def generate_cobertura_xml(rootdir, db, exec_id, output_file):
    """Generate a Cobertura XML coverage report from testmon data."""
    use_lines = db.has_line_data(exec_id)

    if use_lines:
        file_lines = db.fetch_all_file_lines(exec_id)
    else:
        file_lines = None

    file_checksums = db.fetch_all_file_checksums(exec_id)

    all_filenames = set(file_checksums.keys())
    if file_lines:
        all_filenames |= set(file_lines.keys())

    total_lines_valid = 0
    total_lines_covered = 0

    packages = {}

    for filename in sorted(all_filenames):
        filepath = os.path.join(rootdir, filename)
        if not os.path.exists(filepath):
            continue

        if use_lines and filename in file_lines:
            covered_lines = file_lines[filename]
            executable = _get_executable_lines(rootdir, filename)
            if executable is not None:
                all_lines = executable
                covered_lines = covered_lines & executable
                covered_lines = _infer_declaration_coverage(
                    rootdir, filename, covered_lines, all_lines
                )
            else:
                all_lines = covered_lines.copy()
        else:
            checksums = file_checksums.get(filename, set())
            covered_lines, all_lines = get_file_coverage_from_checksums(
                rootdir, filename, checksums
            )

        if not all_lines:
            continue

        dirname = os.path.dirname(filename)
        package_name = dirname.replace(os.sep, ".") if dirname else "."

        if package_name not in packages:
            packages[package_name] = []

        packages[package_name].append(
            (filename, covered_lines, all_lines)
        )

        total_lines_valid += len(all_lines)
        total_lines_covered += len(covered_lines)

    line_rate = total_lines_covered / total_lines_valid if total_lines_valid else 0

    coverage_el = ET.Element("coverage")
    coverage_el.set("version", "1.0")
    coverage_el.set("timestamp", str(int(time.time() * 1000)))
    coverage_el.set("lines-valid", str(total_lines_valid))
    coverage_el.set("lines-covered", str(total_lines_covered))
    coverage_el.set("line-rate", f"{line_rate:.4f}")
    coverage_el.set("branches-valid", "0")
    coverage_el.set("branches-covered", "0")
    coverage_el.set("branch-rate", "0")
    coverage_el.set("complexity", "0")

    sources_el = ET.SubElement(coverage_el, "sources")
    source_el = ET.SubElement(sources_el, "source")
    source_el.text = rootdir

    packages_el = ET.SubElement(coverage_el, "packages")

    for package_name, files in sorted(packages.items()):
        pkg_lines_valid = 0
        pkg_lines_covered = 0

        package_el = ET.SubElement(packages_el, "package")
        package_el.set("name", package_name)
        package_el.set("branch-rate", "0")
        package_el.set("complexity", "0")

        classes_el = ET.SubElement(package_el, "classes")

        for filename, covered_lines, all_lines in sorted(files):
            class_name = os.path.basename(filename)
            file_line_rate = (
                len(covered_lines) / len(all_lines)
                if all_lines
                else 0
            )

            class_el = ET.SubElement(classes_el, "class")
            class_el.set("name", class_name)
            class_el.set("filename", filename)
            class_el.set("line-rate", f"{file_line_rate:.4f}")
            class_el.set("branch-rate", "0")
            class_el.set("complexity", "0")

            ET.SubElement(class_el, "methods")

            lines_el = ET.SubElement(class_el, "lines")
            for line_num in sorted(all_lines):
                line_el = ET.SubElement(lines_el, "line")
                line_el.set("number", str(line_num))
                line_el.set("hits", "1" if line_num in covered_lines else "0")

            pkg_lines_valid += len(all_lines)
            pkg_lines_covered += len(covered_lines)

        pkg_line_rate = (
            pkg_lines_covered / pkg_lines_valid if pkg_lines_valid else 0
        )
        package_el.set("line-rate", f"{pkg_line_rate:.4f}")

    tree = ET.ElementTree(coverage_el)
    ET.indent(tree, space="  ")
    with open(os.path.join(rootdir, output_file), "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)

    return os.path.join(rootdir, output_file)
