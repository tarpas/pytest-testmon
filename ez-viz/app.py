"""
Testmon Multi-Project/Job Visualization Server

This server manages testmon data for multiple repositories and jobs,
allowing clients to upload/download their .testmondata files via API.
"""

from flask import Flask, request, jsonify, send_file, render_template
from pathlib import Path
import sqlite3
import json
import shutil
import os
from typing import Optional, Dict, List
from datetime import datetime
import hashlib

app = Flask(__name__)

# Configuration
BASE_DATA_DIR = Path(os.getenv('TESTMON_DATA_DIR', './testmon_data'))
BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Metadata storage
METADATA_FILE = BASE_DATA_DIR / 'metadata.json'


def get_metadata() -> Dict:
    """Load metadata about all repos and jobs"""
    if METADATA_FILE.exists():
        with open(METADATA_FILE, 'r') as f:
            return json.load(f)
    return {'repos': {}}


def save_metadata(metadata: Dict):
    """Save metadata about all repos and jobs"""
    with open(METADATA_FILE, 'w') as f:
        json.dump(metadata, f, indent=2)


def get_repo_path(repo_id: str) -> Path:
    """Get path for a repository's data directory"""
    # Sanitize repo_id to prevent path traversal
    safe_repo_id = hashlib.sha256(repo_id.encode()).hexdigest()[:16]
    repo_path = BASE_DATA_DIR / safe_repo_id
    repo_path.mkdir(parents=True, exist_ok=True)
    return repo_path


def get_job_db_path(repo_id: str, job_id: str) -> Path:
    """Get path for a specific job's testmon database"""
    repo_path = get_repo_path(repo_id)
    # Sanitize job_id
    safe_job_id = "".join(c for c in job_id if c.isalnum() or c in ('-', '_'))
    job_path = repo_path / safe_job_id
    job_path.mkdir(parents=True, exist_ok=True)
    return job_path / '.testmondata'


def register_repo_job(repo_id: str, job_id: str, repo_name: Optional[str] = None):
    """Register a new repo/job combination in metadata"""
    metadata = get_metadata()

    if repo_id not in metadata['repos']:
        metadata['repos'][repo_id] = {
            'name': repo_name or repo_id,
            'created': datetime.utcnow().isoformat(),
            'jobs': {}
        }

    if job_id not in metadata['repos'][repo_id]['jobs']:
        metadata['repos'][repo_id]['jobs'][job_id] = {
            'created': datetime.utcnow().isoformat(),
            'last_updated': datetime.utcnow().isoformat(),
            'upload_count': 0
        }

    save_metadata(metadata)


def get_db_connection(db_path: Path, readonly: bool = True):
    """Get a connection to a testmon database"""
    mode = 'ro' if readonly else 'rwc'
    return sqlite3.connect(
        f"file:{db_path}?mode={mode}",
        uri=True,
        timeout=60
    )


# ============================================================================
# API ENDPOINTS - Client Operations (GitHub Actions)
# ============================================================================

@app.route('/api/client/upload', methods=['POST'])
def upload_testmon_data():
    """
    Upload testmon data from a client (GitHub Action)

    Request body (multipart/form-data):
        - file: .testmondata file
        - repo_id: Repository identifier (e.g., "owner/repo")
        - job_id: Job identifier (e.g., "test-python-3.11")
        - repo_name: (optional) Human-readable repository name

    Returns:
        JSON with success status and message
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    repo_id = request.form.get('repo_id')
    job_id = request.form.get('job_id')
    repo_name = request.form.get('repo_name')

    if not repo_id or not job_id:
        return jsonify({'error': 'repo_id and job_id are required'}), 400

    try:
        # Register the repo/job if new
        register_repo_job(repo_id, job_id, repo_name)

        # Save the uploaded file
        db_path = get_job_db_path(repo_id, job_id)
        file.save(db_path)

        # Update metadata
        metadata = get_metadata()
        metadata['repos'][repo_id]['jobs'][job_id]['last_updated'] = datetime.utcnow().isoformat()
        metadata['repos'][repo_id]['jobs'][job_id]['upload_count'] += 1
        save_metadata(metadata)

        return jsonify({
            'success': True,
            'message': f'Testmon data uploaded for {repo_id}/{job_id}',
            'db_path': str(db_path.relative_to(BASE_DATA_DIR))
        }), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/client/download', methods=['GET'])
def download_testmon_data():
    """
    Download testmon data for a client (GitHub Action)

    Query parameters:
        - repo_id: Repository identifier
        - job_id: Job identifier

    Returns:
        .testmondata file as attachment
    """
    repo_id = request.args.get('repo_id')
    job_id = request.args.get('job_id')

    if not repo_id or not job_id:
        return jsonify({'error': 'repo_id and job_id are required'}), 400

    db_path = get_job_db_path(repo_id, job_id)

    if not db_path.exists():
        return jsonify({'error': 'No data found for this repo/job'}), 404

    return send_file(
        db_path,
        as_attachment=True,
        download_name='.testmondata',
        mimetype='application/octet-stream'
    )


@app.route('/api/client/exists', methods=['GET'])
def check_testmon_data_exists():
    """
    Check if testmon data exists for a repo/job

    Query parameters:
        - repo_id: Repository identifier
        - job_id: Job identifier

    Returns:
        JSON with exists status
    """
    repo_id = request.args.get('repo_id')
    job_id = request.args.get('job_id')

    if not repo_id or not job_id:
        return jsonify({'error': 'repo_id and job_id are required'}), 400

    db_path = get_job_db_path(repo_id, job_id)

    return jsonify({
        'exists': db_path.exists(),
        'repo_id': repo_id,
        'job_id': job_id
    })


# ============================================================================
# API ENDPOINTS - Visualization Data
# ============================================================================

@app.route('/api/repos', methods=['GET'])
def list_repos():
    """List all repositories with their jobs"""
    metadata = get_metadata()

    repos = []
    for repo_id, repo_data in metadata['repos'].items():
        jobs = []
        for job_id, job_data in repo_data['jobs'].items():
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

    return jsonify({'repos': repos})


@app.route('/api/data/<repo_id>/<job_id>/summary', methods=['GET'])
def get_summary(repo_id: str, job_id: str):
    """Get summary statistics for a specific repo/job"""
    db_path = get_job_db_path(repo_id, job_id)

    if not db_path.exists():
        return jsonify({'error': 'No data found'}), 404

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get environment info
        env = cursor.execute("""
            SELECT environment_name, python_version, system_packages
            FROM environment
            LIMIT 1
        """).fetchone()

        # Count tests
        test_count = cursor.execute("SELECT COUNT(*) FROM test_execution").fetchone()[0]

        # Count files
        file_count = cursor.execute("SELECT COUNT(DISTINCT filename) FROM file_fp").fetchone()[0]

        # Get metadata (savings stats)
        metadata_cursor = cursor.execute("SELECT dataid, data FROM metadata")
        savings = {}
        for row in metadata_cursor:
            if 'tests_saved' in row['dataid'] or 'time_saved' in row['dataid']:
                key = row['dataid'].split(':', 1)[1]
                savings[key] = json.loads(row['data'])

        conn.close()

        return jsonify({
            'repo_id': repo_id,
            'job_id': job_id,
            'test_count': test_count,
            'file_count': file_count,
            'environment': {
                'name': env['environment_name'] if env else 'default',
                'python_version': env['python_version'] if env else 'unknown',
                'packages': env['system_packages'][:100] + '...' if env and env['system_packages'] else ''
            },
            'savings': savings
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/<repo_id>/<job_id>/tests', methods=['GET'])
def get_tests(repo_id: str, job_id: str):
    """Get all tests for a specific repo/job"""
    db_path = get_job_db_path(repo_id, job_id)

    if not db_path.exists():
        return jsonify({'error': 'No data found'}), 404

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

        return jsonify({
            'tests': [dict(test) for test in tests]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/<repo_id>/<job_id>/test/<int:test_id>', methods=['GET'])
def get_test_details(repo_id: str, job_id: str, test_id: int):
    """Get detailed information about a specific test"""
    db_path = get_job_db_path(repo_id, job_id)

    if not db_path.exists():
        return jsonify({'error': 'No data found'}), 404

    try:
        conn = get_db_connection(db_path, readonly=True)
        conn.row_factory = sqlite3.Row

        # Get test info
        test = conn.execute("""
            SELECT * FROM test_execution WHERE id = ?
        """, (test_id,)).fetchone()

        if not test:
            conn.close()
            return jsonify({'error': 'Test not found'}), 404

        # Get dependencies
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

        # Convert checksums blob to list
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

        return jsonify({
            'test': dict(test),
            'dependencies': dependencies
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/data/<repo_id>/<job_id>/files', methods=['GET'])
def get_files(repo_id: str, job_id: str):
    """Get all files tracked for a specific repo/job"""
    db_path = get_job_db_path(repo_id, job_id)

    if not db_path.exists():
        return jsonify({'error': 'No data found'}), 404

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

        return jsonify({
            'files': [dict(file) for file in files]
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# WEB INTERFACE
# ============================================================================

@app.route('/')
def index():
    """Serve the main visualization interface"""
    return render_template('index.html')


@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'data_dir': str(BASE_DATA_DIR),
        'repo_count': len(get_metadata().get('repos', {}))
    })


if __name__ == '__main__':
    print(f"Starting Testmon Multi-Project Server")
    print(f"Data directory: {BASE_DATA_DIR.absolute()}")
    print(f"Server running on http://localhost:8000")
    app.run(debug=True, host='0.0.0.0', port=8000)