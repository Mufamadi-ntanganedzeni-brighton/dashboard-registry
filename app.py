from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3

app = Flask(__name__)
CORS(app)

DB = "dashboard_registry.db"


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS dashboards (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            description TEXT,
            url         TEXT NOT NULL,
            category    TEXT NOT NULL,
            owner_name  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'Unknown'
                        CHECK(status IN ('Up','Down','Unknown')),
            created_at  TEXT NOT NULL DEFAULT (date('now')),
            updated_at  TEXT NOT NULL DEFAULT (date('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS data_sources (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            type        TEXT NOT NULL CHECK(type IN ('Database','File','API')),
            description TEXT
        )
    """)

    # links dashboards to data sources - many to many relationship
    c.execute("""
        CREATE TABLE IF NOT EXISTS dashboard_data_sources (
            dashboard_id   INTEGER NOT NULL REFERENCES dashboards(id),
            data_source_id INTEGER NOT NULL REFERENCES data_sources(id),
            PRIMARY KEY (dashboard_id, data_source_id)
        )
    """)

    if not c.execute("SELECT 1 FROM data_sources LIMIT 1").fetchone():
        sources = [
            ("Sales PostgreSQL DB", "Database", "Primary sales transactional database, updated hourly."),
            ("Monthly HR Export",   "File",     "CSV export from SAP HR system, refreshed monthly."),
            ("Finance ERP API",     "API",      "REST API from the SAP Finance ERP system."),
            ("Operations Log DB",   "Database", "Operational events and SLA tracking database."),
            ("Marketing Analytics", "API",      "Google Analytics and social media stats aggregator."),
        ]
        c.executemany("INSERT INTO data_sources (name, type, description) VALUES (?,?,?)", sources)

    if not c.execute("SELECT 1 FROM dashboards LIMIT 1").fetchone():
        dashboards = [
            ("Monthly Sales Overview", "Shows revenue, deals closed, and pipeline health by region.",
             "https://bi.company.com/sales/monthly", "Sales", "Sales Team", "Up"),
            ("Staff Headcount Report", "Monthly headcount, attrition rate, and new hires by department.",
             "https://bi.company.com/hr/headcount", "HR", "HR Department", "Up"),
            ("Finance P&L Dashboard",  "Profit and loss statement, expense breakdown, and budget vs actuals.",
             "https://bi.company.com/finance/pnl", "Finance", "CFO Office", "Up"),
            ("Operations SLA Tracker", "SLA compliance, ticket volumes, and resolution times.",
             "https://bi.company.com/ops/sla", "Operations", "IT Operations", "Down"),
            ("Executive Summary",      "High-level KPIs across all departments for C-level briefings.",
             "https://bi.company.com/exec/summary", "Executive", "Strategy Office", "Up"),
        ]
        for row in dashboards:
            c.execute(
                "INSERT INTO dashboards (name, description, url, category, owner_name, status) VALUES (?,?,?,?,?,?)",
                row
            )
        links = [(1,1),(1,3),(2,2),(3,3),(4,4),(5,1),(5,2),(5,3),(5,4)]
        c.executemany(
            "INSERT OR IGNORE INTO dashboard_data_sources (dashboard_id, data_source_id) VALUES (?,?)",
            links
        )

    conn.commit()
    conn.close()


def valid_url(url):
    return url and (url.startswith("http://") or url.startswith("https://"))


def dashboard_with_sources(conn, dashboard_id):
    row = conn.execute("SELECT * FROM dashboards WHERE id=?", (dashboard_id,)).fetchone()
    if not row:
        return None
    d = dict(row)
    sources = conn.execute("""
        SELECT ds.id, ds.name, ds.type
        FROM data_sources ds
        JOIN dashboard_data_sources dds ON ds.id = dds.data_source_id
        WHERE dds.dashboard_id = ?
    """, (dashboard_id,)).fetchall()
    d["data_sources"] = [dict(s) for s in sources]
    return d


def save_links(conn, dashboard_id, source_ids):
    conn.execute("DELETE FROM dashboard_data_sources WHERE dashboard_id=?", (dashboard_id,))
    for sid in source_ids:
        conn.execute(
            "INSERT OR IGNORE INTO dashboard_data_sources (dashboard_id, data_source_id) VALUES (?,?)",
            (dashboard_id, sid)
        )


@app.route("/api/dashboards", methods=["GET"])
def get_dashboards():
    search   = request.args.get("search",   "").strip()
    category = request.args.get("category", "").strip()
    status   = request.args.get("status",   "").strip()

    query  = "SELECT id FROM dashboards WHERE 1=1"
    params = []

    if search:
        query += " AND name LIKE ?"
        params.append(f"%{search}%")
    if category:
        query += " AND category=?"
        params.append(category)
    if status:
        query += " AND status=?"
        params.append(status)

    query += " ORDER BY name"

    conn   = get_db()
    ids    = [r["id"] for r in conn.execute(query, params).fetchall()]
    result = [dashboard_with_sources(conn, i) for i in ids]
    conn.close()
    return jsonify(result)


@app.route("/api/dashboards/<int:dashboard_id>", methods=["GET"])
def get_dashboard(dashboard_id):
    conn = get_db()
    d    = dashboard_with_sources(conn, dashboard_id)
    conn.close()
    if not d:
        return jsonify({"error": "Dashboard not found"}), 404
    return jsonify(d)


@app.route("/api/dashboards", methods=["POST"])
def create_dashboard():
    data        = request.get_json()
    name        = (data.get("name")        or "").strip()
    url         = (data.get("url")         or "").strip()
    category    = (data.get("category")    or "").strip()
    owner_name  = (data.get("owner_name")  or "").strip()
    description = (data.get("description") or "").strip()
    status      = data.get("status", "Unknown")
    source_ids  = data.get("data_source_ids", [])

    errors = {}
    if not name:             errors["name"]       = "Name is required."
    if not url:              errors["url"]        = "URL is required."
    elif not valid_url(url): errors["url"]        = "URL must start with http:// or https://"
    if not category:         errors["category"]   = "Category is required."
    if not owner_name:       errors["owner_name"] = "Owner name is required."
    if status not in ("Up", "Down", "Unknown"):
        errors["status"] = "Status must be Up, Down, or Unknown."
    if errors:
        return jsonify({"errors": errors}), 422

    conn = get_db()
    if conn.execute("SELECT 1 FROM dashboards WHERE LOWER(name)=LOWER(?)", (name,)).fetchone():
        conn.close()
        return jsonify({"errors": {"name": "A dashboard with this name already exists."}}), 422

    try:
        cur    = conn.execute(
            "INSERT INTO dashboards (name, description, url, category, owner_name, status) VALUES (?,?,?,?,?,?)",
            (name, description, url, category, owner_name, status)
        )
        new_id = cur.lastrowid
        save_links(conn, new_id, source_ids)
        conn.commit()
        d = dashboard_with_sources(conn, new_id)
        conn.close()
        return jsonify(d), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboards/<int:dashboard_id>", methods=["PUT"])
def update_dashboard(dashboard_id):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM dashboards WHERE id=?", (dashboard_id,)).fetchone():
        conn.close()
        return jsonify({"error": "Dashboard not found"}), 404

    data        = request.get_json()
    name        = (data.get("name")        or "").strip()
    url         = (data.get("url")         or "").strip()
    category    = (data.get("category")    or "").strip()
    owner_name  = (data.get("owner_name")  or "").strip()
    description = (data.get("description") or "").strip()
    status      = data.get("status", "Unknown")
    source_ids  = data.get("data_source_ids", [])

    errors = {}
    if not name:             errors["name"]       = "Name is required."
    if not url:              errors["url"]        = "URL is required."
    elif not valid_url(url): errors["url"]        = "URL must start with http:// or https://"
    if not category:         errors["category"]   = "Category is required."
    if not owner_name:       errors["owner_name"] = "Owner name is required."
    if errors:
        conn.close()
        return jsonify({"errors": errors}), 422

    if conn.execute(
        "SELECT 1 FROM dashboards WHERE LOWER(name)=LOWER(?) AND id!=?", (name, dashboard_id)
    ).fetchone():
        conn.close()
        return jsonify({"errors": {"name": "A dashboard with this name already exists."}}), 422

    try:
        conn.execute(
            "UPDATE dashboards SET name=?, description=?, url=?, category=?, owner_name=?, status=?, updated_at=date('now') WHERE id=?",
            (name, description, url, category, owner_name, status, dashboard_id)
        )
        save_links(conn, dashboard_id, source_ids)
        conn.commit()
        d = dashboard_with_sources(conn, dashboard_id)
        conn.close()
        return jsonify(d)
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/dashboards/<int:dashboard_id>", methods=["DELETE"])
def delete_dashboard(dashboard_id):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM dashboards WHERE id=?", (dashboard_id,)).fetchone():
        conn.close()
        return jsonify({"error": "Dashboard not found"}), 404
    try:
        conn.execute("DELETE FROM dashboard_data_sources WHERE dashboard_id=?", (dashboard_id,))
        conn.execute("DELETE FROM dashboards WHERE id=?", (dashboard_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/data-sources", methods=["GET"])
def get_data_sources():
    search = request.args.get("search", "").strip()
    conn   = get_db()
    if search:
        rows = conn.execute(
            "SELECT * FROM data_sources WHERE name LIKE ? ORDER BY name",
            (f"%{search}%",)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM data_sources ORDER BY name").fetchall()

    result = []
    for row in rows:
        ds   = dict(row)
        used = conn.execute("""
            SELECT d.id, d.name, d.status FROM dashboards d
            JOIN dashboard_data_sources dds ON d.id = dds.dashboard_id
            WHERE dds.data_source_id = ?
        """, (ds["id"],)).fetchall()
        ds["used_by"] = [dict(r) for r in used]
        result.append(ds)

    conn.close()
    return jsonify(result)


@app.route("/api/data-sources/<int:source_id>", methods=["GET"])
def get_data_source(source_id):
    conn = get_db()
    row  = conn.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "Data source not found"}), 404
    ds   = dict(row)
    used = conn.execute("""
        SELECT d.id, d.name, d.status FROM dashboards d
        JOIN dashboard_data_sources dds ON d.id = dds.dashboard_id
        WHERE dds.data_source_id = ?
    """, (source_id,)).fetchall()
    ds["used_by"] = [dict(r) for r in used]
    conn.close()
    return jsonify(ds)


@app.route("/api/data-sources", methods=["POST"])
def create_data_source():
    data        = request.get_json()
    name        = (data.get("name")        or "").strip()
    type_       = (data.get("type")        or "").strip()
    description = (data.get("description") or "").strip()

    errors = {}
    if not name: errors["name"] = "Name is required."
    if type_ not in ("Database", "File", "API"):
        errors["type"] = "Type must be Database, File, or API."
    if errors:
        return jsonify({"errors": errors}), 422

    conn = get_db()
    if conn.execute("SELECT 1 FROM data_sources WHERE LOWER(name)=LOWER(?)", (name,)).fetchone():
        conn.close()
        return jsonify({"errors": {"name": "A data source with this name already exists."}}), 422

    try:
        cur    = conn.execute(
            "INSERT INTO data_sources (name, type, description) VALUES (?,?,?)",
            (name, type_, description)
        )
        new_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM data_sources WHERE id=?", (new_id,)).fetchone()
        conn.close()
        return jsonify({**dict(row), "used_by": []}), 201
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/data-sources/<int:source_id>", methods=["PUT"])
def update_data_source(source_id):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM data_sources WHERE id=?", (source_id,)).fetchone():
        conn.close()
        return jsonify({"error": "Data source not found"}), 404

    data        = request.get_json()
    name        = (data.get("name")        or "").strip()
    type_       = (data.get("type")        or "").strip()
    description = (data.get("description") or "").strip()

    errors = {}
    if not name: errors["name"] = "Name is required."
    if type_ not in ("Database", "File", "API"):
        errors["type"] = "Type must be Database, File, or API."
    if errors:
        conn.close()
        return jsonify({"errors": errors}), 422

    if conn.execute(
        "SELECT 1 FROM data_sources WHERE LOWER(name)=LOWER(?) AND id!=?", (name, source_id)
    ).fetchone():
        conn.close()
        return jsonify({"errors": {"name": "A data source with this name already exists."}}), 422

    try:
        conn.execute(
            "UPDATE data_sources SET name=?, type=?, description=? WHERE id=?",
            (name, type_, description, source_id)
        )
        conn.commit()
        row = conn.execute("SELECT * FROM data_sources WHERE id=?", (source_id,)).fetchone()
        conn.close()
        return jsonify(dict(row))
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


@app.route("/api/data-sources/<int:source_id>", methods=["DELETE"])
def delete_data_source(source_id):
    conn = get_db()
    if not conn.execute("SELECT 1 FROM data_sources WHERE id=?", (source_id,)).fetchone():
        conn.close()
        return jsonify({"error": "Data source not found"}), 404

    count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM dashboard_data_sources WHERE data_source_id=?",
        (source_id,)
    ).fetchone()["cnt"]

    if count > 0:
        conn.close()
        return jsonify({
            "error": f"This data source is linked to {count} dashboard(s). Remove those links first."
        }), 409

    try:
        conn.execute("DELETE FROM data_sources WHERE id=?", (source_id,))
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    init_db()
    print("Server running at http://localhost:5000")
    app.run(debug=True, port=5000)
