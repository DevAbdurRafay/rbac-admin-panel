from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import psycopg2, psycopg2.extras, psycopg2.errors
import os, re
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="HR Admin API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory="static"), name="static")

DATABASE_URL = os.getenv("DATABASE_URL")

def _clean_url(url: str) -> str:
    return re.sub(r'^postgresql\+[^:]+://', 'postgresql://', url)

def admin_conn():
    return psycopg2.connect(_clean_url(DATABASE_URL))

def _parse_dsn(url: str) -> dict:
    url = _clean_url(url)
    url = re.sub(r'^postgres(?:ql)?://', '', url)
    params = {}
    if '?' in url:
        url, qs = url.split('?', 1)
        for part in qs.split('&'):
            if '=' in part:
                k, v = part.split('=', 1)
                params[k] = v
    m = re.match(r'(?:([^:@]*)(?::([^@]*))?@)?([^/:]+)(?::(\d+))?(?:/(.*))?$', url)
    if not m:
        raise ValueError("Cannot parse DATABASE_URL")
    user, password, host, port, dbname = m.groups()
    dsn = {"host": host, "dbname": dbname or "postgres", "sslmode": params.get("sslmode", "require")}
    if user:     dsn["user"]     = user
    if password: dsn["password"] = password
    if port:     dsn["port"]     = int(port)
    return dsn

def get_admin_password() -> str:
    return _parse_dsn(DATABASE_URL).get("password", "")

def user_conn(username: str, password: str):
    dsn = _parse_dsn(DATABASE_URL)
    dsn["user"]     = username
    dsn["password"] = password
    return psycopg2.connect(**dsn)

class ToggleReq(BaseModel):
    role: str; table: str; priv: str; action: str; admin_password: str

class UserSqlReq(BaseModel):
    username: str
    password: str
    sql: str

class AdminSqlReq(BaseModel):
    sql: str
    admin_password: str

class CreateUserReq(BaseModel):
    username: str
    password: str
    role: str
    admin_password: str

class DeleteUserReq(BaseModel):
    username: str
    admin_password: str

class VerifyReq(BaseModel):
    username: str
    password: str

@app.get("/", response_class=HTMLResponse)
def root():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "admin.html")
    if os.path.exists(path):
        return HTMLResponse(open(path, encoding="utf-8").read())
    return HTMLResponse("<h2>admin.html not found in templates/ folder</h2>", status_code=404)

@app.get("/api/health")
def health():
    try:
        c = admin_conn(); c.cursor().execute("SELECT 1"); c.close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(503, str(e))

@app.get("/api/stats")
def stats():
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM employees;")
        total = cur.fetchone()[0]
        cur.execute("""
            SELECT department, COUNT(*) AS cnt,
                   ROUND(AVG(monthly_income)::numeric, 0) AS avg_sal
            FROM employees GROUP BY department ORDER BY cnt DESC;
        """)
        depts = [{"dept": r[0], "total": r[1], "avg_sal": int(r[2] or 0)} for r in cur.fetchall()]
        return {"total_employees": total, "departments": depts}
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cur.close(); conn.close()

SKIP_USERS = {
    "postgres","supabase_admin","authenticator","supabase_auth_admin",
    "supabase_storage_admin","dashboard_user","pgbouncer","anon",
    "authenticated","service_role","pgsodium_keyholder",
    "supabase_replication_admin","supabase_read_only_user", "supabase_etl_admin"
}

@app.get("/api/users")
def list_users():
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT u.usename,
                   ARRAY_AGG(DISTINCT m.rolname) FILTER (WHERE m.rolname LIKE '%_role') AS roles
            FROM pg_user u
            LEFT JOIN pg_auth_members am ON am.member = u.usesysid
            LEFT JOIN pg_roles m ON m.oid = am.roleid
            GROUP BY u.usename ORDER BY u.usename;
        """)
        return [{"username": r[0], "roles": r[1] or []}
                for r in cur.fetchall() if r[0] not in SKIP_USERS]
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cur.close(); conn.close()

@app.get("/api/roles")
def list_roles():
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE '%_role' ORDER BY rolname;")
        return [r[0] for r in cur.fetchall()]
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cur.close(); conn.close()

@app.post("/api/users/create")
def create_user(req: CreateUserReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{1,30}$', req.username):
        return {"ok": False, "error": "Invalid username (alphanumeric + underscore, start with letter)"}
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute(f"CREATE USER {req.username} WITH PASSWORD %s;", (req.password,))
        cur.execute(f"GRANT {req.role} TO {req.username};")
        conn.commit()
        return {"ok": True, "message": f"User '{req.username}' created with role '{req.role}'"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.post("/api/users/delete")
def delete_user(req: DeleteUserReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]{1,30}$', req.username):
        return {"ok": False, "error": "Invalid username"}
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute(f"DROP USER IF EXISTS {req.username};")
        conn.commit()
        return {"ok": True, "message": f"User '{req.username}' deleted"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.get("/api/privileges")
def privileges():
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            SELECT grantee, table_name, privilege_type
            FROM information_schema.role_table_grants
            WHERE table_schema = 'public' AND grantee LIKE '%_role'
            ORDER BY grantee, table_name, privilege_type;
        """)
        result = {}
        for grantee, table, priv in cur.fetchall():
            result.setdefault(grantee, {}).setdefault(table, [])
            result[grantee][table].append(priv)
        return result
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cur.close(); conn.close()

@app.post("/api/toggle")
def toggle(req: ToggleReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "detail": "Wrong admin password"}
    kw  = "TO" if req.action == "GRANT" else "FROM"
    sql = f"{req.action} {req.priv} ON {req.table} {kw} {req.role}"
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute(sql); conn.commit()
        return {"ok": True, "sql": sql}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "detail": str(e), "sql": sql}
    finally:
        cur.close(); conn.close()

@app.post("/api/verify")
def verify_user(req: VerifyReq):
    try:
        c = user_conn(req.username, req.password); c.close()
        return {"ok": True}
    except Exception:
        return {"ok": False}

def _manual_audit(conn, username: str, action: str, table: str, detail: str):
    try:
        c = conn.cursor()
        c.execute("""
            INSERT INTO audit_log(username, action, table_name, record_id, detail, executed_at)
            VALUES (%s, %s, %s, '-', %s, NOW())
        """, (username, action, table, detail))
        c.close()
    except Exception:
        pass

BLOCKED_PREFIXES = (
    "GRANT", "REVOKE", "CREATE", "DROP", "ALTER",
    "TRUNCATE", "VACUUM", "ANALYZE", "CLUSTER",
    "COMMENT", "SECURITY", "REASSIGN", "IMPORT",
    "COPY", "LISTEN", "NOTIFY", "UNLISTEN",
    "LOAD", "RESET", "SET ROLE", "SET SESSION"
)

def _is_blocked(stmt: str) -> bool:
    """Return True if the statement starts with any admin-only keyword."""
    upper = stmt.strip().upper()
    return any(upper.startswith(kw) for kw in BLOCKED_PREFIXES)

@app.post("/api/sql")
def user_sql(req: UserSqlReq):
    try:
        conn = user_conn(req.username, req.password)
    except Exception:
        return {"results": [{"ok": False, "error": "AUTH_FAILED",
                              "detail": "Wrong username or password.", "sql": ""}]}

    init_cur = conn.cursor()
    init_cur.execute("SELECT set_config('app.current_user', %s, false)", (req.username,))
    init_cur.close()

    stmts = [s.strip() for s in req.sql.split(";") if s.strip()]
    results = []

    for stmt in stmts:
        
        if _is_blocked(stmt):
            results.append({
                "ok": False,
                "type": "permission",
                "error": "PERMISSION DENIED",
                "detail": (
                    f"'{req.username}' is not allowed to run "
                    f"{stmt.strip().split()[0].upper()} statements. "
                    "Only SELECT, INSERT, UPDATE, DELETE are permitted for non-admin users."
                ),
                "sql": stmt
            })
            continue

        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(stmt)
            upper = stmt.strip().upper()

            if cur.description:
                rows = [dict(r) for r in cur.fetchall()]
                cols = [d.name for d in cur.description]
                tbl_match = re.search(r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)', stmt, re.IGNORECASE)
                tbl_name  = tbl_match.group(1) if tbl_match else 'unknown'
                
                conn.commit()
                _manual_audit(conn, req.username, 'SELECT', tbl_name, f"SELECT on {tbl_name} — {len(rows)} row(s) returned")
                conn.commit()
                
                results.append({"ok": True, "type": "select", "columns": cols, "rows": rows, "rowcount": len(rows), "sql": stmt})
            else:
                action_word = upper.split()[0]
                tbl_match = re.search(r'\b(?:INTO|FROM|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)', stmt, re.IGNORECASE)
                tbl_name = tbl_match.group(1) if tbl_match else 'unknown'
                row_count = cur.rowcount
    
                if row_count == 0:
                    conn.rollback()
                    results.append({"ok": False, "type": "not_found", "error": "NOT FOUND", "detail": f"No matching record found — 0 rows affected. Check if the ID or condition exists in '{tbl_name}'.", "sql": stmt})
                else:
                    conn.commit()
                    results.append({"ok": True, "type": "dml", "columns": [], "rows": [], "rowcount": row_count, "message": f"✓ {row_count} row(s) affected — saved to database", "sql": stmt})

        except psycopg2.errors.InsufficientPrivilege:
            conn.rollback()
            results.append({"ok": False, "type": "permission", "error": "PERMISSION DENIED",
                             "detail": f"'{req.username}' does not have this privilege on the requested table.",
                             "sql": stmt})
        except Exception as e:
            conn.rollback()
            results.append({"ok": False, "type": "error", "error": str(e), "sql": stmt})
        finally:
            cur.close()

    conn.close()
    return {"results": results}

@app.post("/api/admin/sql")
def admin_sql(req: AdminSqlReq):
    if req.admin_password != get_admin_password():
        return {"results": [{"ok": False, "error": "Wrong admin password", "sql": ""}]}
    conn = admin_conn()
    stmts = [s.strip() for s in req.sql.split(";") if s.strip()]
    results = []
    for stmt in stmts:
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(stmt)
            if cur.description:
                rows = [dict(r) for r in cur.fetchall()]
                cols = [d.name for d in cur.description]
                conn.commit()
                results.append({"ok": True, "type": "select", "columns": cols,
                                 "rows": rows, "rowcount": len(rows), "sql": stmt})
            else:
                row_count = cur.rowcount
                conn.commit()
                results.append({"ok": True, "type": "dml", "columns": [], "rows": [],
                                 "rowcount": row_count,
                                 "message": f"✓ {row_count} row(s) affected", "sql": stmt})
        except Exception as e:
            conn.rollback()
            results.append({"ok": False, "error": str(e), "sql": stmt})
        finally:
            cur.close()
    conn.close()
    return {"results": results}

# ── Audit log ────────────────────────────────────────────────────────
@app.get("/api/audit")
def audit_log():
    conn = admin_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    dsn_user = _parse_dsn(DATABASE_URL).get("user", "postgres")
    try:
        cur.execute("""
            SELECT username, action, table_name, detail,
                   executed_at AT TIME ZONE 'Asia/Karachi' as ts
            FROM audit_log
            WHERE username NOT IN %s
            ORDER BY executed_at DESC LIMIT 200;
        """, ((dsn_user, "postgres", "supabase_admin"),))
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        cur.close(); conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)