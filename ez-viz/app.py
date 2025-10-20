"""
Testmon Multi-Project/Job Visualization Server with Extensive Logging
"""

from flask import Flask, request, jsonify, send_file, render_template, g
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

# -----------------------------------------------------------------------------
# Logging setup
# -----------------------------------------------------------------------------
def setup_logging(level: int = logging.INFO):
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="ts=%(asctime)s level=%(levelname)s req_id=%(request_id)s "
            "event=%(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    # Avoid duplicate handlers if reloaded
    for h in list(root.handlers):
        root.removeHandler(h)

    root.addHandler(handler)
    root.setLevel(level)

class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Attach request_id if present (Flask request context), else '-'
        record.request_id = getattr(g, "request_id", "-") if _has_request_ctx() else "-"
        return True

def _has_request_ctx():
    # Safe check without importing Flask internals
    try:
        return bool(getattr(g, "_flask_app_ctx_stack", None) or True)  # g is proxy, will exist
    except Exception:
        return False

setup_logging()
logging.getLogger().addFilter(RequestIdFilter())
log = logging.getLogger("testmon")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def human_bytes(n: int) -> str:
    units = ["B","KB","MB","GB","TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units)-1:
        f /= 1024.0
        i += 1
    return f"{f:.2f}{units[i]}"

def log_exception(context: str, **extra):
    log.error(f"{context} error={type(sys.exc_info()[1]).__name__} "
              f"detail={sys.exc_info()[1]} extra={extra}")

def now_iso() -> str:
    return datetime.utcnow().isoformat()

# -----------------------------------------------------------------------------
# Flask app + config
# -----------------------------------------------------------------------------
app = Flask(__name__)

BASE_DATA_DIR = Path(os.getenv('TESTMON_DATA_DIR', './testmon_data'))
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
METADATA_FILE = BASE_DATA_DIR / 'metadata.json'

# -----------------------------------------------------------------------------
# Request lifecycle logging
# -----------------------------------------------------------------------------
@app.before_request
def add_request_context():
    g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    g.t_start = time.perf_counter()
    log.info(
        "request_started "
        f"method={request.method} path={request.path} "
        f"remote_addr={request.remote_addr} ua={request.user_agent}"
    )

@app.after_request
def after(resp):
    latency_ms = int((time.perf_counter() - getattr(g, "t_start", time.perf_counter())) * 1000)
    log.info(
        "request_finished "
        f"method={request.method} path={request.path} status={resp.status_code} "
        f"latency_ms={latency_ms}"
    )
    resp.headers["X-Request-ID"] = g.request_id
    return resp

@app.teardown_request
def teardown_request(exc):
    if exc:
        # Log uncaught exceptions
        log.error(f"unhandled_exception path={request.path} exc={exc} trace={traceback.format_exc()}")

# -----------------------------------------------------------------------------
# Metadata storage with logging
# -----------------------------------------------------------------------------
def get_metadata() -> Dict:
    """Load metadata about all repos and jobs"""
    try:
        if METADATA_FILE.exists():
            log.info(f"metadata_read_attempt path={METADATA_FILE}")
            with open(METADATA_FILE, 'r') as f:
                data = json.load(f)
            size = METADATA_FILE.stat().st_size
            log.info(f"metadata_read_success path={METADATA_FILE} size={size} ({human_bytes(size)})")
            return data
        else:
            log.info(f"metadata_missing path={METADATA_FILE}")
            return {'repos': {}}
    except Exception:
        log_exception("metadata_read", path=str(METADATA_FILE))
        return {'repos': {}}

def save_metadata(metadata: Dict):
    """Save metadata about all repos and jobs"""
    try:
        tmp = METADATA_FILE.with_suffix(".json.tmp")
        log.info(f"metadata_write_attempt path={METADATA_FILE} tmp={tmp}")
        with open(tmp, 'w') as f:
            json.dump(metadata, f, indent=2)
        os.replace(tmp, METADATA_FILE)  # atomic on POSIX
        size = METADATA_FILE.stat().st_size
        log.info(f"metadata_write_success path={METADATA_FILE} size={size} ({human_bytes(size)})")
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
        log.info(f"repo_dir_create_attempt repo_id={repo_id} safe_repo={safe_repo_id} path={repo_path}")
        repo_path.mkdir(parents=True, exist_ok=True)
        log.info(f"repo_dir_create_success path={repo_path}")
    return repo_path

def get_job_db_path(repo_id: str, job_id: str) -> Path:
    """Get path for a specific job's testmon database"""
    repo_path = get_repo_path(repo_id)
    safe_job_id = "".join(c for c in job_id if c.isalnum() or c in ('-', '_'))
    job_path = repo_path / safe_job_id
    if not job_path.exists():
        log.info(f"job_dir_create_attempt repo_id={repo_id} job_id={job_id} safe_job_id={safe_job_id} path={job_path}")
        job_path.mkdir(parents=True, exist_ok=True)
        log.info(f"job_dir_create_success path={job_path}")
    db_path = job_path / '.testmondata'
    log.info(f"job_db_resolve repo_id={repo_id} job_id={job_id} db_path={db_path}")
    return db_path

def register_repo_job(repo_id: str, job_id: str, repo_name: Optional[str] = None):
    """Register a new repo/job combination in metadata"""
    try:
        log.info(f"register_repo_job repo_id={repo_id} job_id={job_id} repo_name={repo_name}")
        metadata = get_metadata()

        if repo_id not in metadata['repos']:
            metadata['repos'][repo_id] = {
                'name': repo_name or repo_id,
                'created': now_iso(),
                'jobs': {}
            }
            log.info(f"metadata_add_repo repo_id={repo_id}")

        if job_id not in metadata['repos'][repo_id]['jobs']:
            metadata['repos'][repo_id]['jobs'][job_id] = {
                'created': now_iso(),
                'last_updated': now_iso(),
                'upload_count': 0
            }
            log.info(f"metadata_add_job repo_id={repo_id} job_id={job_id}")

        save_metadata(metadata)
    except Exception:
        log_exception("register_repo_job", repo_id=repo_id, job_id=job_id)

# -----------------------------------------------------------------------------
# SQLite with logging
# -----------------------------------------------------------------------------
def get_db_connection(db_path: Path, readonly: bool = True):
    """Get a connection to a testmon database"""
    mode = 'ro' if readonly else 'rwc'
    log.info(f"db_connect_attempt path={db_path} readonly={readonly} mode={mode}")
    try:
        conn = sqlite3.connect(
            f"file:{db_path}?mode={mode}",
            uri=True,
            timeout=60
        )
        log.info(f"db_connect_success path={db_path}")
        return conn
    except Exception:
        log_exception("db_connect", path=str(db_path), readonly=readonly, mode=mode)
        raise

# -----------------------------------------------------------------------------
# API ENDPOINTS - Client Operations (GitHub Actions)
# -----------------------------------------------------------------------------
@app.route('/api/client/upload', methods=['POST'])
def upload_testmon_data():
    if 'file' not in request.files:
        log.warning("upload_missing_file")
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    repo_id = request.form.get('repo_id')
    job_id = request.form.get('job_id')
    repo_name = request.form.get('repo_name')

    log.info(f"upload_received repo_id={repo_id} job_id={job_id} filename={getattr(file, 'filename', None)}")

    if not repo_id or not job_id:
        log.warning("upload_missing_params")
        return jsonify({'error': 'repo_id and job_id are required'}), 400

    try:
        register_repo_job(repo_id, job_id, repo_name)

        db_path = get_job_db_path(repo_id, job_id)

        # Attempt to write uploaded file
        log.info(f"file_write_attempt repo_id={repo_id} job_id={job_id} dest={db_path}")
        file.save(db_path)
        size = db_path.stat().st_size
        log.info(f"file_write_success dest={db_path} size={size} ({human_bytes(size)})")

        # Update metadata
        metadata = get_metadata()
        metadata['repos'][repo_id]['jobs'][job_id]['last_updated'] = now_iso()
        metadata['repos'][repo_id]['jobs'][job_id]['upload_count'] += 1
        save_metadata(metadata)
        log.info(f"upload_metadata_updated repo_id={repo_id} job_id={job_id}")

        return jsonify({
            'success': True,
            'message': f'Testmon data uploaded for {repo_id}/{job_id}',
            'db_path': str(db_path.relative_to(BASE_DATA_DIR))
        }), 200

    except Exception:
        log_exception("upload_handler", repo_id=repo_id, job_id=job_id)
        return jsonify({'error': 'Upload failed'}), 500

@app.route('/api/client/download', methods=['GET'])
def download_testmon_data():
    repo_id = request.args.get('repo_id')
    job_id = request.args.get('job_id')
    log.info(f"download_request repo_id={repo_id} job_id={job_id}")

    if not repo_id or not job_id:
        log.warning("download_missing_params")
        return jsonify({'error': 'repo_id and job_id are required'}), 400

    db_path = get_job_db_path(repo_id, job_id)

    log.info(f"file_read_attempt repo_id={repo_id} job_id={job_id} path={db_path}")
    if not db_path.exists():
        log.warning(f"file_read_not_found path={db_path}")
        return jsonify({'error': 'No data found for this repo/job'}), 404

    try:
        size = db_path.stat().st_size
        log.info(f"file_read_success path={db_path} size={size} ({human_bytes(size)})")
        return send_file(
            db_path,
            as_attachment=True,
            download_name='.testmondata',
            mimetype='application/octet-stream'
        )
    except Exception:
        log_exception("download_send_file", path=str(db_path))
        return jsonify({'error': 'Failed to send file'}), 500

@app.route('/api/client/exists', methods=['GET'])
def check_testmon_data_exists():
    repo_id = request.args.get('repo_id')
    job_id = request.args.get('job_id')
    log.info(f"exists_request repo_id={repo_id} job_id={job_id}")

    if not repo_id or not job_id:
        log.warning("exists_missing_params")
        return jsonify({'error': 'repo_id and job_id are required'}), 400

    db_path = get_job_db_path(repo_id, job_id)
    exists = db_path.exists()
    log.info(f"exists_checked path={db_path} exists={exists}")

    return jsonify({
        'exists': exists,
        'repo_id': repo_id,
        'job_id': job_id
    })

# -----------------------------------------------------------------------------
# API ENDPOINTS - Visualization Data (with DB logging)
# -----------------------------------------------------------------------------
def _open_db_or_404(repo_id: str, job_id: str):
    db_path = get_job_db_path(repo_id, job_id)
    log.info(f"db_read_attempt path={db_path}")
    if not db_path.exists():
        log.warning(f"db_missing path={db_path}")
        return None, jsonify({'error': 'No data found'}), 404
    return db_path, None, None

@app.route('/api/repos', methods=['GET'])
def list_repos():
    log.info("repos_list_attempt")
    metadata = get_metadata()

    repos = []
    for repo_id, repo_data in metadata.get('repos', {}).items():
        jobs = []
        for job_id, job_data in repo_data.get('jobs', {}).items():
            jobs.append({
                'id': job_id,
                'created': job_data['created'],
                'last_updated': job_data['last_updated'],
                'upload_count': job_data['upload_count']
            })
        repos.append({
            'id': repo_id,
            'name': repo_data['name'],
            'created': repo_data['created'],
            'jobs': jobs
        })
    log.info(f"repos_list_success count={len(repos)}")
    return jsonify({'repos': repos})

@app.route('/api/data/<repo_id>/<job_id>/summary', methods=['GET'])
def get_summary(repo_id: str, job_id: str):
    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        env = cursor.execute("""
            SELECT environment_name, python_version, system_packages
            FROM environment
            LIMIT 1
        """).fetchone()

        test_count = cursor.execute("SELECT COUNT(*) FROM test_execution").fetchone()[0]
        file_count = cursor.execute("SELECT COUNT(DISTINCT filename) FROM file_fp").fetchone()[0]

        metadata_cursor = cursor.execute("SELECT dataid, data FROM metadata")
        savings = {}
        for row in metadata_cursor:
            if 'tests_saved' in row['dataid'] or 'time_saved' in row['dataid']:
                key = row['dataid'].split(':', 1)[1]
                savings[key] = json.loads(row['data'])

        conn.close()
        log.info(f"summary_success repo_id={repo_id} job_id={job_id} tests={test_count} files={file_count}")

        return jsonify({
            'repo_id': repo_id,
            'job_id': job_id,
            'test_count': test_count,
            'file_count': file_count,
            'environment': {
                'name': env['environment_name'] if env else 'default',
                'python_version': env['python_version'] if env else 'unknown',
                'packages': (env['system_packages'][:100] + '...') if env and env['system_packages'] else ''
            },
            'savings': savings
        })

    except Exception:
        log_exception("summary_query", repo_id=repo_id, job_id=job_id)
        return jsonify({'error': 'Failed to read summary'}), 500

@app.route('/api/data/<repo_id>/<job_id>/tests', methods=['GET'])
def get_tests(repo_id: str, job_id: str):
    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row

        tests = conn.execute("""
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
        """).fetchall()

        conn.close()
        log.info(f"tests_list_success repo_id={repo_id} job_id={job_id} count={len(tests)}")

        return jsonify({'tests': [dict(test) for test in tests]})

    except Exception:
        log_exception("tests_query", repo_id=repo_id, job_id=job_id)
        return jsonify({'error': 'Failed to read tests'}), 500

@app.route('/api/data/<repo_id>/<job_id>/test/<int:test_id>', methods=['GET'])
def get_test_details(repo_id: str, job_id: str, test_id: int):
    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row

        test = conn.execute("SELECT * FROM test_execution WHERE id = ?", (test_id,)).fetchone()
        if not test:
            conn.close()
            log.warning(f"test_not_found repo_id={repo_id} job_id={job_id} test_id={test_id}")
            return jsonify({'error': 'Test not found'}), 404

        deps = conn.execute("""
            SELECT 
                fp.filename,
                fp.fsha,
                fp.method_checksums,
                fp.mtime
            FROM test_execution_file_fp tef
            JOIN file_fp fp ON tef.fingerprint_id = fp.id
            WHERE tef.test_execution_id = ?
        """, (test_id,)).fetchall()

        conn.close()

        import array
        dependencies = []
        for dep in deps:
            checksums_arr = array.array('i')
            checksums_arr.frombytes(dep['method_checksums'])
            dependencies.append({
                'filename': dep['filename'],
                'fsha': dep['fsha'],
                'mtime': dep['mtime'],
                'checksums': checksums_arr.tolist()
            })

        log.info(f"test_details_success repo_id={repo_id} job_id={job_id} test_id={test_id} deps={len(dependencies)}")
        return jsonify({'test': dict(test), 'dependencies': dependencies})

    except Exception:
        log_exception("test_details_query", repo_id=repo_id, job_id=job_id, test_id=test_id)
        return jsonify({'error': 'Failed to read test details'}), 500

@app.route('/api/data/<repo_id>/<job_id>/files', methods=['GET'])
def get_files(repo_id: str, job_id: str):
    db_path, resp, code = _open_db_or_404(repo_id, job_id)
    if resp:
        return resp, code

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row

        files = conn.execute("""
            SELECT 
                fp.filename,
                COUNT(DISTINCT tef.test_execution_id) as test_count,
                COUNT(DISTINCT fp.id) as fingerprint_count
            FROM file_fp fp
            LEFT JOIN test_execution_file_fp tef ON fp.id = tef.fingerprint_id
            GROUP BY fp.filename
            ORDER BY fp.filename
        """).fetchall()

        conn.close()
        log.info(f"files_list_success repo_id={repo_id} job_id={job_id} count={len(files)}")

        return jsonify({'files': [dict(file) for file in files]})

    except Exception:
        log_exception("files_query", repo_id=repo_id, job_id=job_id)
        return jsonify({'error': 'Failed to read files'}), 500

# -----------------------------------------------------------------------------
# WEB + Health
# -----------------------------------------------------------------------------
@app.route('/')
def index():
    log.info("index_render")
    return render_template('index.html')

@app.route('/health')
def health():
    repo_count = len(get_metadata().get('repos', {}))
    log.info(f"health_check repo_count={repo_count} data_dir={BASE_DATA_DIR}")
    return jsonify({
        'status': 'healthy!',
        'data_dir': str(BASE_DATA_DIR),
        'repo_count': repo_count
    })

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    log.info(f"server_start data_dir={BASE_DATA_DIR.absolute()}")
    print(f"Starting Testmon Multi-Project Server")
    print(f"Data directory: {BASE_DATA_DIR.absolute()}")
    print(f"Server running on http://localhost:8000")
    app.run(debug=True, host='0.0.0.0', port=8000)
