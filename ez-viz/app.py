"""
Testmon Multi-Project/Job Visualization Server with Extensive Logging
"""

from flask import (
    Flask,
    request,
    jsonify,
    send_file,
    send_from_directory,
    g,
    has_request_context,
)

from pathlib import Path

import sqlite3
import json
import os
from typing import Optional, Dict
from datetime import datetime
import hashlib
import logging
import sys
import time
import uuid
import traceback

EZMON_FP_DIR = Path(os.getenv("EZMON_FP_DIR", "./.ezmon-fp")).resolve()
# -----------------------------------------------------------------------------
# Logging helpers
# -----------------------------------------------------------------------------
def human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    return f"{f:.2f}{units[i]}"

def now_iso() -> str:
    return datetime.utcnow().isoformat()

def log_exception(context: str, **extra):
    exc_type, exc, _ = sys.exc_info()
    logging.getLogger("testmon").error(
        f"{context} error={getattr(exc_type, '__name__', 'Exception')} detail={exc} extra={extra}"
    )

# -----------------------------------------------------------------------------
# Logging setup (safe for Werkzeug/gunicorn records)
# -----------------------------------------------------------------------------
class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Safe defaults for all records (startup, gunicorn, werkzeug, etc.)
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        if not hasattr(record, "repo_id"):
            record.repo_id = "-"
        if not hasattr(record, "job_id"):
            record.job_id = "-"

        # If we’re inside a Flask request, enrich from g
        try:
            if has_request_context():
                record.request_id = getattr(g, "request_id", record.request_id)
                record.repo_id = getattr(g, "repo_id", record.repo_id)
                record.job_id = getattr(g, "job_id", record.job_id)
        except Exception:
            # Never let logging crash the app
            pass
        return True

def setup_logging(level=logging.INFO):
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt=(
            "ts=%(asctime)s level=%(levelname)s req_id=%(request_id)s "
            "repo=%(repo_id)s job=%(job_id)s event=%(message)s"
        ),
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)
    handler.addFilter(ContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

setup_logging()
log = logging.getLogger("testmon")

# -----------------------------------------------------------------------------
# Flask app + config
# -----------------------------------------------------------------------------
app = Flask(__name__)

BASE_DATA_DIR = Path(os.getenv("TESTMON_DATA_DIR", "./testmon_data"))
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
METADATA_FILE = BASE_DATA_DIR / "metadata.json"

# -----------------------------------------------------------------------------
# Request lifecycle logging
# -----------------------------------------------------------------------------
@app.before_request
def seed_request_context():
    # Correlation + defaults (repo/job filled by endpoints when known)
    g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    g.repo_id = "-"
    g.job_id = "-"
    g.t_start = time.perf_counter()
    log.info(
        "request_started method=%s path=%s remote_addr=%s ua=%s",
        request.method,
        request.path,
        request.remote_addr,
        request.user_agent,
    )

@app.after_request
def after(resp):
    latency_ms = int(
        (time.perf_counter() - getattr(g, "t_start", time.perf_counter())) * 1000
    )
    log.info(
        "request_finished method=%s path=%s status=%s latency_ms=%s",
        request.method,
        request.path,
        resp.status_code,
        latency_ms,
    )
    resp.headers["X-Request-ID"] = g.request_id
    return resp

@app.teardown_request
def teardown_request(exc):
    if exc:
        # Log uncaught exceptions
        log.error(
            "unhandled_exception path=%s exc=%s trace=%s",
            request.path,
            exc,
            traceback.format_exc(),
        )

# -----------------------------------------------------------------------------
# Metadata storage with logging
# -----------------------------------------------------------------------------
def get_metadata() -> Dict:
    """Load metadata about all repos and jobs"""
    try:
        if METADATA_FILE.exists():
            log.info("metadata_read_attempt path=%s", METADATA_FILE)
            with open(METADATA_FILE, "r") as f:
                data = json.load(f)
            size = METADATA_FILE.stat().st_size
            log.info(
                "metadata_read_success path=%s size=%s (%s)",
                METADATA_FILE,
                size,
                human_bytes(size),
            )
            return data
        else:
            log.info("metadata_missing path=%s", METADATA_FILE)
            return {"repos": {}}
    except Exception:
        log_exception("metadata_read", path=str(METADATA_FILE))
        return {"repos": {}}

def save_metadata(metadata: Dict):
    """Save metadata about all repos and jobs"""
    try:
        tmp = METADATA_FILE.with_suffix(".json.tmp")
        log.info("metadata_write_attempt path=%s tmp=%s", METADATA_FILE, tmp)
        with open(tmp, "w") as f:
            json.dump(metadata, f, indent=2)
        os.replace(tmp, METADATA_FILE)  # atomic on POSIX
        size = METADATA_FILE.stat().st_size
        log.info(
            "metadata_write_success path=%s size=%s (%s)",
            METADATA_FILE,
            size,
            human_bytes(size),
        )
    except Exception:
        log_exception("metadata_write", path=str(METADATA_FILE))

# -----------------------------------------------------------------------------
# Path helpers with logging
# -----------------------------------------------------------------------------
def get_repo_path(repo_id: str) -> Path:
    """Get path for a repository's data directory"""
    safe_repo_id = hashlib.sha256(repo_id.encode()).hexdigest()[:16]
    repo_path = BASE_DATA_DIR / safe_repo_id
    if not repo_path.exists():
        log.info(
            "repo_dir_create_attempt repo_id=%s safe_repo=%s path=%s",
            repo_id,
            safe_repo_id,
            repo_path,
        )
        repo_path.mkdir(parents=True, exist_ok=True)
        log.info("repo_dir_create_success path=%s", repo_path)
    return repo_path

def get_job_db_path(repo_id: str, job_id: str) -> Path:
    """Get path for a specific job's testmon database"""
    repo_path = get_repo_path(repo_id)
    safe_job_id = "".join(c for c in job_id if c.isalnum() or c in ("-", "_"))
    job_path = repo_path / safe_job_id
    if not job_path.exists():
        log.info(
            "job_dir_create_attempt repo_id=%s job_id=%s safe_job_id=%s path=%s",
            repo_id,
            job_id,
            safe_job_id,
            job_path,
        )
        job_path.mkdir(parents=True, exist_ok=True)
        log.info("job_dir_create_success path=%s", job_path)
    db_path = job_path / ".testmondata"
    log.info("job_db_resolve repo_id=%s job_id=%s db_path=%s", repo_id, job_id, db_path)
    return db_path

def register_repo_job(repo_id: str, job_id: str, repo_name: Optional[str] = None):
    """Register a new repo/job combination in metadata"""
    try:
        log.info(
            "register_repo_job repo_id=%s job_id=%s repo_name=%s",
            repo_id,
            job_id,
            repo_name,
        )
        metadata = get_metadata()

        if repo_id not in metadata["repos"]:
            metadata["repos"][repo_id] = {
                "name": repo_name or repo_id,
                "created": now_iso(),
                "jobs": {},
            }
            log.info("metadata_add_repo repo_id=%s", repo_id)

        if job_id not in metadata["repos"][repo_id]["jobs"]:
            metadata["repos"][repo_id]["jobs"][job_id] = {
                "created": now_iso(),
                "last_updated": now_iso(),
                "upload_count": 0,
            }
            log.info("metadata_add_job repo_id=%s job_id=%s", repo_id, job_id)

        save_metadata(metadata)
    except Exception:
        log_exception("register_repo_job", repo_id=repo_id, job_id=job_id)

# -----------------------------------------------------------------------------
# SQLite with logging
# -----------------------------------------------------------------------------
def get_db_connection(db_path: Path, readonly: bool = True):
    """Get a connection to a testmon database"""
    mode = "ro" if readonly else "rwc"
    log.info("db_connect_attempt path=%s readonly=%s mode=%s", db_path, readonly, mode)
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode={mode}", uri=True, timeout=60)
        log.info("db_connect_success path=%s", db_path)
        return conn
    except Exception:
        log_exception("db_connect", path=str(db_path), readonly=readonly, mode=mode)
        raise

# -----------------------------------------------------------------------------
# API ENDPOINTS - Client Operations (GitHub Actions)
# -----------------------------------------------------------------------------
@app.route("/api/client/upload", methods=["POST"])
def upload_testmon_data():
    file = request.files.get("file")
    repo_id = request.form.get("repo_id")
    job_id = request.form.get("job_id")
    repo_name = request.form.get("repo_name")

    # Enrich per-request context for logging
    g.repo_id, g.job_id = repo_id or "-", job_id or "-"

    if not file:
        log.warning("upload_missing_file")
        return jsonify({"error": "No file provided"}), 400

    log.info(
        "upload_received filename=%s", getattr(file, "filename", None)
    )

    if not repo_id or not job_id:
        log.warning("upload_missing_params")
        return jsonify({"error": "repo_id and job_id are required"}), 400

    try:
        register_repo_job(repo_id, job_id, repo_name)

        db_path = get_job_db_path(repo_id, job_id)

        # Attempt to write uploaded file
        log.info("file_write_attempt dest=%s", db_path)
        file.save(db_path)
        size = db_path.stat().st_size
        log.info("file_write_success dest=%s size=%s (%s)", db_path, size, human_bytes(size))

        # Update metadata
        metadata = get_metadata()
        metadata["repos"][repo_id]["jobs"][job_id]["last_updated"] = now_iso()
        metadata["repos"][repo_id]["jobs"][job_id]["upload_count"] += 1
        save_metadata(metadata)
        log.info("upload_metadata_updated")

        return jsonify(
            {
                "success": True,
                "message": f"Testmon data uploaded for {repo_id}/{job_id}",
                "db_path": str(db_path.relative_to(BASE_DATA_DIR)),
            }
        ), 200

    except Exception:
        log_exception("upload_handler", repo_id=repo_id, job_id=job_id)
        return jsonify({"error": "Upload failed"}), 500

@app.route("/api/client/download", methods=["GET"])
def download_testmon_data():
    repo_id = request.args.get("repo_id")
    job_id = request.args.get("job_id")
    g.repo_id, g.job_id = repo_id or "-", job_id or "-"

    log.info("download_request")

    if not repo_id or not job_id:
        log.warning("download_missing_params")
        return jsonify({"error": "repo_id and job_id are required"}), 400

    db_path = get_job_db_path(repo_id, job_id)

    log.info("file_read_attempt path=%s", db_path)
    if not db_path.exists():
        log.warning("file_read_not_found path=%s", db_path)
        return jsonify({"error": "No data found for this repo/job"}), 404

    try:
        size = db_path.stat().st_size
        log.info("file_read_success path=%s size=%s (%s)", db_path, size, human_bytes(size))
        return send_file(
            db_path,
            as_attachment=True,
            download_name=".testmondata",
            mimetype="application/octet-stream",
        )
    except Exception:
        log_exception("download_send_file", path=str(db_path))
        return jsonify({"error": "Failed to send file"}), 500

@app.route("/api/client/exists", methods=["GET"])
def check_testmon_data_exists():
    repo_id = request.args.get("repo_id")
    job_id = request.args.get("job_id")
    g.repo_id, g.job_id = repo_id or "-", job_id or "-"

    log.info("exists_request")

    if not repo_id or not job_id:
        log.warning("exists_missing_params")
        return jsonify({"error": "repo_id and job_id are required"}), 400

    db_path = get_job_db_path(repo_id, job_id)
    exists = db_path.exists()
    log.info("exists_checked path=%s exists=%s", db_path, exists)

    return jsonify({"exists": exists, "repo_id": repo_id, "job_id": job_id})

# -----------------------------------------------------------------------------
# API ENDPOINTS - Visualization Data (with DB logging)
# -----------------------------------------------------------------------------
def _open_db_or_404(repo_id: str, job_id: str):
    db_path = get_job_db_path(repo_id, job_id)
    log.info("db_read_attempt path=%s", db_path)
    if not db_path.exists():
        log.warning("db_missing path=%s", db_path)
        return None, jsonify({"error": "No data found"}), 404
    return db_path, None, None

@app.route("/api/repos", methods=["GET"])
def list_repos():
    log.info("repos_list_attempt")
    metadata = get_metadata()

    repos = []
    for repo_id, repo_data in metadata.get("repos", {}).items():
        jobs = []
        for job_id, job_data in repo_data.get("jobs", {}).items():
            jobs.append(
                {
                    "id": job_id,
                    "created": job_data["created"],
                    "last_updated": job_data["last_updated"],
                    "upload_count": job_data["upload_count"],
                }
            )
        repos.append(
            {
                "id": repo_id,
                "name": repo_data["name"],
                "created": repo_data["created"],
                "jobs": jobs,
            }
        )
    log.info("repos_list_success count=%s", len(repos))
    return jsonify({"repos": repos})

@app.route('/api/data/<path:repo_id>/<job_id>/summary', methods=['GET'])
def get_summary(repo_id: str, job_id: str):
    g.repo_id, g.job_id = repo_id, job_id

    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        env = cursor.execute(
            """
            SELECT environment_name, python_version, system_packages
            FROM environment
            LIMIT 1
        """
        ).fetchone()

        test_count = cursor.execute("SELECT COUNT(*) FROM test_execution").fetchone()[0]
        file_count = cursor.execute(
            "SELECT COUNT(DISTINCT filename) FROM file_fp"
        ).fetchone()[0]

        metadata_cursor = cursor.execute("SELECT dataid, data FROM metadata")
        savings = {}
        for row in metadata_cursor:
            if "tests_saved" in row["dataid"] or "time_saved" in row["dataid"]:
                key = row["dataid"].split(":", 1)[1]
                savings[key] = json.loads(row["data"])

        conn.close()
        log.info(
            "summary_success tests=%s files=%s",
            test_count,
            file_count,
        )

        return jsonify(
            {
                "repo_id": repo_id,
                "job_id": job_id,
                "test_count": test_count,
                "file_count": file_count,
                "environment": {
                    "name": env["environment_name"] if env else "default",
                    "python_version": env["python_version"] if env else "unknown",
                    "packages": (env["system_packages"][:100] + "...")
                    if env and env["system_packages"]
                    else "",
                },
                "savings": savings,
            }
        )

    except Exception:
        log_exception("summary_query", repo_id=repo_id, job_id=job_id)
        return jsonify({"error": "Failed to read summary"}), 500

@app.route("/api/data/<path:repo_id>/<job_id>/tests", methods=["GET"])
def get_tests(repo_id: str, job_id: str):
    g.repo_id, g.job_id = repo_id, job_id

    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row

        tests = conn.execute(
            """
            SELECT 
                te.id,
                te.test_name,
                te.duration,
                te.failed,
                te.forced,
                COUNT(DISTINCT tef.fingerprint_id) as dependency_count
            FROM test_execution te
            LEFT JOIN test_execution_file_fp tef ON te.id = tef.test_execution_id
            GROUP BY te.id, te.test_name, te.duration, te.failed, te.forced
            ORDER BY te.test_name
        """
        ).fetchall()

        conn.close()
        log.info("tests_list_success count=%s", len(tests))

        return jsonify({"tests": [dict(test) for test in tests]})

    except Exception:
        log_exception("tests_query", repo_id=repo_id, job_id=job_id)
        return jsonify({"error": "Failed to read tests"}), 500

@app.route("/api/data/<path:repo_id>/<job_id>/test/<int:test_id>", methods=["GET"])
def get_test_details(repo_id: str, job_id: str, test_id: int):
    g.repo_id, g.job_id = repo_id, job_id

    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row

        test = conn.execute(
            "SELECT * FROM test_execution WHERE id = ?", (test_id,)
        ).fetchone()
        if not test:
            conn.close()
            log.warning("test_not_found test_id=%s", test_id)
            return jsonify({"error": "Test not found"}), 404

        deps = conn.execute(
            """
            SELECT 
                fp.filename,
                fp.fsha,
                fp.method_checksums,
                fp.mtime
            FROM test_execution_file_fp tef
            JOIN file_fp fp ON tef.fingerprint_id = fp.id
            WHERE tef.test_execution_id = ?
        """,
            (test_id,),
        ).fetchall()

        conn.close()

        import array

        dependencies = []
        for dep in deps:
            checksums_arr = array.array("i")
            checksums_arr.frombytes(dep["method_checksums"])
            dependencies.append(
                {
                    "filename": dep["filename"],
                    "fsha": dep["fsha"],
                    "mtime": dep["mtime"],
                    "checksums": checksums_arr.tolist(),
                }
            )

        log.info("test_details_success test_id=%s deps=%s", test_id, len(dependencies))
        return jsonify({"test": dict(test), "dependencies": dependencies})

    except Exception:
        log_exception("test_details_query", repo_id=repo_id, job_id=job_id, test_id=test_id)
        return jsonify({"error": "Failed to read test details"}), 500

@app.route("/api/data/<path:repo_id>/<job_id>/files", methods=["GET"])
def get_files(repo_id: str, job_id: str):
    g.repo_id, g.job_id = repo_id, job_id

    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row

        files = conn.execute(
            """
            SELECT 
                fp.filename,
                COUNT(DISTINCT tef.test_execution_id) as test_count,
                COUNT(DISTINCT fp.id) as fingerprint_count
            FROM file_fp fp
            LEFT JOIN test_execution_file_fp tef ON fp.id = tef.fingerprint_id
            GROUP BY fp.filename
            ORDER BY fp.filename
        """
        ).fetchall()

        conn.close()
        log.info("files_list_success count=%s", len(files))

        return jsonify({"files": [dict(file) for file in files]})

    except Exception:
        log_exception("files_query", repo_id=repo_id, job_id=job_id)
        return jsonify({"error": "Failed to read files"}), 500


@app.route("/api/client/testPreferences", methods=["POST"])
def upload_test_preferences():
    """Store user's test preferences (which tests to always run)"""
    
    # Get data from request body (JSON)
    data = request.get_json()
    log.info("data is" , data)
    repo_id = data.get("repo_id")
    job_id = data.get("job_id")
    
    selected_test_files = data.get("selectedTests", [])  # Array of test file names
    
    # Enrich per-request context for logging
    g.repo_id, g.job_id = repo_id or "-", job_id or "-"

    if not repo_id or not job_id:
        log.warning("preferences_missing_params")
        return jsonify({"error": "repo_id and job_id are required"}), 400

    if not isinstance(selected_test_files, list):
        log.warning("preferences_invalid_format")
        return jsonify({"error": "selectedTests must be an array"}), 400

    try:
        # Create preferences file path
        job_path = get_job_db_path(repo_id, job_id).parent
        preferences_path = job_path / "test_preferences.json"
        
        log.info(
            "preferences_write_attempt path=%s test_count=%s", 
            preferences_path, 
            len(selected_test_files)
        )
        
        # Store preferences as JSON
        preferences_data = {
            "repo_id": repo_id,
            "job_id": job_id,
            "always_run_tests": selected_test_files,
            "updated_at": now_iso(),
        }
        
        with open(preferences_path, "w") as f:
            json.dump(preferences_data, f, indent=2)
        
        size = preferences_path.stat().st_size
        log.info(
            "preferences_write_success path=%s size=%s (%s) test_count=%s",
            preferences_path,
            size,
            human_bytes(size),
            len(selected_test_files)
        )

        return jsonify({
            "success": True,
            "message": f"Test preferences saved for {repo_id}/{job_id}",
            "test_count": len(selected_test_files),
        }), 200

    except Exception:
        log_exception("preferences_handler", repo_id=repo_id, job_id=job_id)
        return jsonify({"error": "Failed to save preferences"}), 500


@app.route("/api/client/testPreferences", methods=["GET"])
def get_test_preferences():
    """Retrieve user's test preferences"""
    
    repo_id = request.args.get("repo_id")
    job_id = request.args.get("job_id")
    g.repo_id, g.job_id = repo_id or "-", job_id or "-"

    if not repo_id or not job_id:
        log.warning("preferences_get_missing_params")
        return jsonify({"error": "repo_id and job_id are required"}), 400

    try:
        job_path = get_job_db_path(repo_id, job_id).parent
        preferences_path = job_path / "test_preferences.json"
        
        log.info("preferences_read_attempt path=%s", preferences_path)
        
        if not preferences_path.exists():
            log.info("preferences_not_found path=%s", preferences_path)
            return jsonify({
                "repo_id": repo_id,
                "job_id": job_id,
                "always_run_tests": [],
                "updated_at": None,
            }), 200
        
        with open(preferences_path, "r") as f:
            preferences_data = json.load(f)
        
        size = preferences_path.stat().st_size
        log.info(
            "preferences_read_success path=%s size=%s (%s)",
            preferences_path,
            size,
            human_bytes(size)
        )
        
        return jsonify(preferences_data), 200

    except Exception:
        log_exception("preferences_get_handler", repo_id=repo_id, job_id=job_id)
        return jsonify({"error": "Failed to read preferences"}), 500
# -----------------------------------------------------------------------------
# WEB + Health - UPDATED FOR REACT
# -----------------------------------------------------------------------------

# Serve React App for root route
@app.route("/")
def serve_react_root():
    react_index = Path(app.root_path) / 'client' / 'dist' / 'index.html'
    log.info("serve_react_root path=%s exists=%s", react_index, react_index.exists())

    if react_index.exists():
        return send_file(react_index)
    else:
        log.error("react_build_missing expected=%s", react_index)
        return jsonify({"error": "React app not built. Run 'npm run build' in client directory"}), 500

# Serve React App's static assets (CSS, JS, images, etc.)
@app.route('/assets/<path:path>')
def serve_react_assets(path):
    assets_dir = Path(app.root_path) / 'client' / 'dist' / 'assets'
    log.info("serve_assets path=%s dir=%s", path, assets_dir)
    return send_from_directory(assets_dir, path)

# Catch-all route for React Router (client-side routing)
@app.route("/<path:path>")
def serve_react_app(path):
    # Don't catch API routes
    if path.startswith('api/'):
        log.warning("invalid_api_route path=%s", path)
        return jsonify({"error": "API endpoint not found"}), 404

    # Don't catch the .ezmon-fp routes
    if path.startswith('.ezmon-fp/'):
        return serve_ezmon_fp(path.replace('.ezmon-fp/', ''))

    # Check if the path is a static file in dist
    file_path = Path(app.root_path) / 'client' / 'dist' / path
    if file_path.exists() and file_path.is_file():
        return send_file(file_path)

    # Otherwise, serve index.html for React Router
    react_index = Path(app.root_path) / 'client' / 'dist' / 'index.html'
    log.info("serve_react_app path=%s", path)

    if react_index.exists():
        return send_file(react_index)
    else:
        log.error("react_build_missing expected=%s", react_index)
        return jsonify({"error": "React app not built"}), 500

@app.route("/health")
def health():
    repo_count = len(get_metadata().get("repos", {}))
    log.info("health_check repo_count=%s data_dir=%s", repo_count, BASE_DATA_DIR)
    return jsonify(
        {"status": "healthy!!!", "data_dir": str(BASE_DATA_DIR), "repo_count": repo_count}
    )

# @app.route("/fingerprints")
# def fingerprints_page():
#     log.info("fingerprints_render")
#     return render_template("fingerprints.html")

@app.route("/.ezmon-fp/<path:subpath>")
def serve_ezmon_fp(subpath: str):
    # Static file bridge for the ezmon snapshots
    fp_path = EZMON_FP_DIR / subpath
    if not fp_path.exists() or fp_path.is_dir():
        log.warning("ezmon_fp_missing path=%s", fp_path)
        return jsonify({"error": "Not found"}), 404
    try:
        size = fp_path.stat().st_size
    except Exception:
        size = -1
    log.info("ezmon_fp_serve path=%s size=%s", fp_path, size)
    return send_from_directory(EZMON_FP_DIR, subpath, as_attachment=False)

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    log.info("server_start data_dir=%s", BASE_DATA_DIR.absolute())
    print("Starting Testmon Multi-Project Server")
    print(f"Data directory: {BASE_DATA_DIR.absolute()}")
    print("Server running on http://localhost:8000")
    app.run(debug=True, host="0.0.0.0", port=8000)
