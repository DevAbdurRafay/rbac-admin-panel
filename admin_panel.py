from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import psycopg2, psycopg2.extras, psycopg2.errors
import os, re
from dotenv import load_dotenv
from typing import Optional

load_dotenv()

app = FastAPI(title="HR Admin API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory="static"), name="static")

DATABASE_URL = os.getenv("DATABASE_URL")

def _clean_url(url: str) -> str:
    return re.sub(r'^postgresql\+[^:]+://', 'postgresql://', url)

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
    # Fixed regex to allow dots (.) in the username for Supabase Pooler strings
    m = re.match(r'(?:([^:@]*)(?::([^@]*))?@)?([^/:]+)(?::(\d+))?(?:/(.*))?$', url)
    if not m:
        raise ValueError("Cannot parse DATABASE_URL")
    user, password, host, port, dbname = m.groups()
    dsn = {"host": host, "dbname": dbname or "postgres", "sslmode": params.get("sslmode", "require")}
    if user:     dsn["user"]     = user
    if password: dsn["password"] = password
    if port:     dsn["port"]     = int(port)
    return dsn

def admin_conn():
    dsn = _parse_dsn(DATABASE_URL)
    dsn["connect_timeout"] = 15
    return psycopg2.connect(**dsn)

def get_admin_password() -> str:
    return _parse_dsn(DATABASE_URL).get("password", "")

def user_conn(username: str, password: str):
    dsn = _parse_dsn(DATABASE_URL)
    main_user = dsn.get("user", "postgres")
    # Appending supabase project ID reference for dynamically created users over connection pooler
    if "." in main_user:
        proj_id = main_user.split(".", 1)[1]
        dsn["user"] = f"{username}.{proj_id}"
    else:
        dsn["user"] = username
    dsn["password"] = password
    dsn["connect_timeout"] = 15
    return psycopg2.connect(**dsn)

# ── Pydantic Models ─────────────────────────────────────────────────
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

class InsertEmployeeReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    id: Optional[int] = None
    emp_id: str
    age: int
    age_group: str
    attrition: str
    department: str
    gender: str
    job_role: str
    monthly_income: float
    salary_slab: str

class UpdateEmployeeReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    id: int
    emp_id: Optional[str] = None
    age: Optional[int] = None
    age_group: Optional[str] = None
    attrition: Optional[str] = None
    department: Optional[str] = None
    gender: Optional[str] = None
    job_role: Optional[str] = None
    monthly_income: Optional[float] = None
    salary_slab: Optional[str] = None

class DeleteEmployeeReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    id: int

class InsertSalaryReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    emp_id: str
    monthly_income: float
    salary_slab: str
    recorded_on: str

class UpdateSalaryReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    id: int
    emp_id: Optional[str] = None
    monthly_income: Optional[float] = None
    salary_slab: Optional[str] = None
    recorded_on: Optional[str] = None

class DeleteSalaryReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    id: int

class InsertDeptReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    dept_name: str

class UpdateDeptReq(BaseModel):
    admin_password: str
    performed_by: Optional[str] = "admin"
    id: int
    dept_name: Optional[str] = None

class DeleteDeptReq(BaseModel):
    admin_password: str
    id: int

# ── HTML Serve ──────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
def root():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "admin.html")
    if os.path.exists(path):
        return HTMLResponse(open(path, encoding="utf-8").read())
    return HTMLResponse("<h2>admin.html not found in templates/ folder</h2>", status_code=404)

# ── Health ──────────────────────────────────────────────────────────
@app.get("/api/health")
def health():
    try:
        c = admin_conn(); c.cursor().execute("SELECT 1"); c.close()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(503, str(e))

# ── Stats ───────────────────────────────────────────────────────────
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

# ── Table Meta ──────────────────────────────────────────────────────
@app.get("/api/table-meta/{table}")
def table_meta(table: str):
    allowed = {"employees", "departments", "salary_records"}
    if table not in allowed:
        raise HTTPException(400, "Invalid table")
    conn = admin_conn(); cur = conn.cursor()
    try:
        meta = {}
        if table == "employees":
            meta["columns"] = ["id","emp_id","age","age_group","attrition","department",
                                "gender","job_role","monthly_income","salary_slab"]
            cur.execute("SELECT DISTINCT id FROM employees ORDER BY id;")
            meta["ids"] = [str(r[0]) for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT emp_id FROM employees ORDER BY emp_id;")
            meta["emp_ids"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT age FROM employees ORDER BY age;")
            meta["ages"] = [str(r[0]) for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT age_group FROM employees WHERE age_group IS NOT NULL ORDER BY age_group;")
            meta["age_groups"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT attrition FROM employees WHERE attrition IS NOT NULL ORDER BY attrition;")
            meta["attritions"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT department FROM employees WHERE department IS NOT NULL ORDER BY department;")
            meta["departments"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT gender FROM employees WHERE gender IS NOT NULL ORDER BY gender;")
            meta["genders"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT job_role FROM employees WHERE job_role IS NOT NULL ORDER BY job_role;")
            meta["job_roles"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT salary_slab FROM employees WHERE salary_slab IS NOT NULL ORDER BY salary_slab;")
            meta["salary_slabs"] = [r[0] for r in cur.fetchall()]

        elif table == "departments":
            meta["columns"] = ["id","dept_name"]
            cur.execute("SELECT DISTINCT id FROM departments ORDER BY id;")
            meta["ids"] = [str(r[0]) for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT dept_name FROM departments WHERE dept_name IS NOT NULL ORDER BY dept_name;")
            meta["dept_names"] = [r[0] for r in cur.fetchall()]

        elif table == "salary_records":
            meta["columns"] = ["id","emp_id","monthly_income","salary_slab","recorded_on"]
            cur.execute("SELECT DISTINCT id FROM salary_records ORDER BY id;")
            meta["ids"] = [str(r[0]) for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT emp_id FROM salary_records ORDER BY emp_id;")
            meta["emp_ids"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT salary_slab FROM salary_records WHERE salary_slab IS NOT NULL ORDER BY salary_slab;")
            meta["salary_slabs"] = [r[0] for r in cur.fetchall()]
            cur.execute("SELECT DISTINCT recorded_on FROM salary_records WHERE recorded_on IS NOT NULL ORDER BY recorded_on DESC LIMIT 100;")
            meta["recorded_ons"] = [str(r[0]) for r in cur.fetchall()]

        return meta
    except Exception as e:
        raise HTTPException(500, str(e))
    finally:
        cur.close(); conn.close()

# ── Users ────────────────────────────────────────────────────────────
SKIP_USERS = {
    "postgres","supabase_admin","authenticator","supabase_auth_admin",
    "supabase_storage_admin","dashboard_user","pgbouncer","anon",
    "authenticated","service_role","pgsodium_keyholder",
    "supabase_replication_admin","supabase_read_only_user","supabase_etl_admin"
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

# ── Privileges ───────────────────────────────────────────────────────
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

# ── Verify ───────────────────────────────────────────────────────────
@app.post("/api/verify")
def verify_user(req: VerifyReq):
    try:
        c = user_conn(req.username, req.password); c.close()
        return {"ok": True}
    except Exception:
        return {"ok": False}

# ── Helpers ──────────────────────────────────────────────────────────
def _manual_audit(conn_ignored, username: str, action: str, table: str, detail: str):
    try:
        ac = admin_conn()
        c  = ac.cursor()
        c.execute("""
            INSERT INTO audit_log(username, action, table_name, record_id, detail, executed_at)
            VALUES (%s, %s, %s, '-', %s, NOW())
        """, (username, action, table, detail))
        ac.commit()
        c.close(); ac.close()
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
    upper = stmt.strip().upper()
    return any(upper.startswith(kw) for kw in BLOCKED_PREFIXES)

def _check_id_exists(conn, table: str, record_id: int) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT 1 FROM {table} WHERE id = %s LIMIT 1;", (record_id,))
        return cur.fetchone() is not None
    finally:
        cur.close()

# ── SQL Execution ─────────────────────────────────────────────────────
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

    SKIP_AUDIT_PATTERNS = ("has_table_privilege", "set_config", "pg_")
    stmts = [s.strip() for s in req.sql.split(";") if s.strip()]
    results = []

    for stmt in stmts:
        if any(p in stmt.lower() for p in SKIP_AUDIT_PATTERNS):
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
                    conn.commit()
                    results.append({"ok": True, "type": "dml", "columns": [], "rows": [],
                                    "rowcount": cur.rowcount, "sql": stmt})
            except Exception as e:
                conn.rollback()
                results.append({"ok": False, "type": "error", "error": str(e), "sql": stmt})
            finally:
                cur.close()
            continue

        if _is_blocked(stmt):
            results.append({
                "ok": False, "type": "permission", "error": "PERMISSION DENIED",
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
                tbl_match = re.search(r'\bFROM\s+(public\.)?([a-zA-Z_][a-zA-Z0-9_]*)', stmt, re.IGNORECASE)
                tbl_name  = tbl_match.group(2) if tbl_match else 'unknown'
                conn.commit()
                _manual_audit(conn, req.username, 'SELECT', tbl_name,
                               f"✓ SUCCESS — {len(rows)} row(s) returned from {tbl_name}")
                results.append({"ok": True, "type": "select", "columns": cols,
                                 "rows": rows, "rowcount": len(rows), "sql": stmt})
            else:
                action_word = upper.split()[0]
                tbl_match = re.search(r'\b(?:INTO|FROM|UPDATE)\s+(public\.)?([a-zA-Z_][a-zA-Z0-9_]*)',
                                       stmt, re.IGNORECASE)
                tbl_name   = tbl_match.group(2) if tbl_match else 'unknown'
                row_count  = cur.rowcount
                if row_count == 0:
                    conn.rollback()
                    results.append({
                        "ok": False, "type": "not_found", "error": "NOT FOUND",
                        "detail": f"No matching record found — 0 rows affected. "
                                  f"Check if the ID or condition exists in '{tbl_name}'.",
                        "sql": stmt
                    })
                else:
                    conn.commit()
                    _manual_audit(conn, req.username, action_word, tbl_name,
                                  f"✓ SUCCESS — {action_word} on {tbl_name}, {row_count} row(s) affected")
                    results.append({
                        "ok": True, "type": "dml", "columns": [], "rows": [],
                        "rowcount": row_count,
                        "message": f"✓ {row_count} row(s) affected — saved to database",
                        "sql": stmt
                    })
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

# ── CRUD: Employees ──────────────────────────────────────────────────
@app.post("/api/employees/insert")
def insert_employee(req: InsertEmployeeReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn(); cur = conn.cursor()
    try:
        if req.id:
            cur.execute("""
                INSERT INTO employees (id, emp_id, age, age_group, attrition, department,
                                       gender, job_role, monthly_income, salary_slab)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id;
            """, (req.id, req.emp_id, req.age, req.age_group, req.attrition, req.department,
                  req.gender, req.job_role, req.monthly_income, req.salary_slab))
        else:
            cur.execute("""
                INSERT INTO employees (emp_id, age, age_group, attrition, department,
                                       gender, job_role, monthly_income, salary_slab)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id;
            """, (req.emp_id, req.age, req.age_group, req.attrition, req.department,
                  req.gender, req.job_role, req.monthly_income, req.salary_slab))
        new_id = cur.fetchone()[0]
        conn.commit()
        _manual_audit(conn, req.performed_by, "INSERT", "employees",
                      f"✓ SUCCESS — Inserted employee emp_id={req.emp_id} → id={new_id}")
        conn.commit()
        return {"ok": True, "message": f"Employee inserted with id={new_id}", "new_id": new_id}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.post("/api/employees/update")
def update_employee(req: UpdateEmployeeReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn()
    if not _check_id_exists(conn, "employees", req.id):
        conn.close()
        return {"ok": False, "error": f"ID {req.id} does not exist in employees table.",
                "type": "not_found"}
    fields = {}
    if req.emp_id        is not None: fields["emp_id"]         = req.emp_id
    if req.age           is not None: fields["age"]            = req.age
    if req.age_group     is not None: fields["age_group"]      = req.age_group
    if req.attrition     is not None: fields["attrition"]      = req.attrition
    if req.department    is not None: fields["department"]     = req.department
    if req.gender        is not None: fields["gender"]         = req.gender
    if req.job_role      is not None: fields["job_role"]       = req.job_role
    if req.monthly_income is not None: fields["monthly_income"] = req.monthly_income
    if req.salary_slab   is not None: fields["salary_slab"]    = req.salary_slab
    if not fields:
        conn.close()
        return {"ok": False, "error": "No fields provided to update"}
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [req.id]
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE employees SET {set_clause} WHERE id = %s;", values)
        conn.commit()
        _manual_audit(conn, req.performed_by, "UPDATE", "employees",
                      f"✓ SUCCESS — Updated employee id={req.id} fields={list(fields.keys())}")
        conn.commit()
        return {"ok": True, "message": f"Employee id={req.id} updated successfully"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.post("/api/employees/delete")
def delete_employee(req: DeleteEmployeeReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn()
    if not _check_id_exists(conn, "employees", req.id):
        conn.close()
        return {"ok": False, "error": f"ID {req.id} does not exist in employees table.",
                "type": "not_found"}
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM employees WHERE id = %s;", (req.id,))
        conn.commit()
        _manual_audit(conn, req.performed_by, "DELETE", "employees",
                      f"✓ SUCCESS — Deleted employee id={req.id}")
        conn.commit()
        return {"ok": True, "message": f"Employee id={req.id} deleted successfully"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

# ── CRUD: Salary Records ─────────────────────────────────────────────
@app.post("/api/salary_records/insert")
def insert_salary(req: InsertSalaryReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO salary_records (emp_id, monthly_income, salary_slab, recorded_on)
            VALUES (%s,%s,%s,%s) RETURNING id;
        """, (req.emp_id, req.monthly_income, req.salary_slab, req.recorded_on))
        new_id = cur.fetchone()[0]
        conn.commit()
        _manual_audit(conn, "admin", "INSERT", "salary_records",
                      f"Inserted salary record emp_id={req.emp_id} → id={new_id}")
        conn.commit()
        return {"ok": True, "message": f"Salary record inserted with id={new_id}", "new_id": new_id}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.post("/api/salary_records/update")
def update_salary(req: UpdateSalaryReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn()
    if not _check_id_exists(conn, "salary_records", req.id):
        conn.close()
        return {"ok": False, "error": f"ID {req.id} does not exist in salary_records table.",
                "type": "not_found"}
    fields = {}
    if req.emp_id         is not None: fields["emp_id"]          = req.emp_id
    if req.monthly_income is not None: fields["monthly_income"]  = req.monthly_income
    if req.salary_slab    is not None: fields["salary_slab"]     = req.salary_slab
    if req.recorded_on    is not None: fields["recorded_on"]     = req.recorded_on
    if not fields:
        conn.close()
        return {"ok": False, "error": "No fields provided to update"}
    set_clause = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [req.id]
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE salary_records SET {set_clause} WHERE id = %s;", values)
        conn.commit()
        _manual_audit(conn, req.performed_by, "UPDATE", "salary_records",
                      f"✓ SUCCESS — Updated salary_record id={req.id}")
        conn.commit()
        return {"ok": True, "message": f"Salary record id={req.id} updated successfully"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.post("/api/salary_records/delete")
def delete_salary(req: DeleteSalaryReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn()
    if not _check_id_exists(conn, "salary_records", req.id):
        conn.close()
        return {"ok": False, "error": f"ID {req.id} does not exist in salary_records table.",
                "type": "not_found"}
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM salary_records WHERE id = %s;", (req.id,))
        conn.commit()
        _manual_audit(conn, req.performed_by, "DELETE", "salary_records",
                      f"✓ SUCCESS — Deleted salary_record id={req.id}")
        conn.commit()
        return {"ok": True, "message": f"Salary record id={req.id} deleted successfully"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

# ── CRUD: Departments ─────────────────────────────────────────────────
@app.post("/api/departments/insert")
def insert_dept(req: InsertDeptReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO departments (dept_name) VALUES (%s) RETURNING id;",
                    (req.dept_name,))
        new_id = cur.fetchone()[0]
        conn.commit()
        _manual_audit(conn, req.performed_by, "INSERT", "departments",
                      f"✓ SUCCESS — Inserted department dept_name={req.dept_name} → id={new_id}")
        conn.commit()
        return {"ok": True, "message": f"Department inserted with id={new_id}", "new_id": new_id}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.post("/api/departments/update")
def update_dept(req: UpdateDeptReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn()
    if not _check_id_exists(conn, "departments", req.id):
        conn.close()
        return {"ok": False, "error": f"ID {req.id} does not exist in departments table.",
                "type": "not_found"}
    if req.dept_name is None:
        conn.close()
        return {"ok": False, "error": "No fields provided to update"}
    cur = conn.cursor()
    try:
        cur.execute("UPDATE departments SET dept_name = %s WHERE id = %s;",
                    (req.dept_name, req.id))
        conn.commit()
        _manual_audit(conn, req.performed_by, "UPDATE", "departments",
                      f"✓ SUCCESS — Updated department id={req.id} dept_name={req.dept_name}")
        conn.commit()
        return {"ok": True, "message": f"Department id={req.id} updated successfully"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

@app.post("/api/departments/delete")
def delete_dept(req: DeleteDeptReq):
    if req.admin_password != get_admin_password():
        return {"ok": False, "error": "Wrong admin password"}
    conn = admin_conn()
    if not _check_id_exists(conn, "departments", req.id):
        conn.close()
        return {"ok": False, "error": f"ID {req.id} does not exist in departments table.",
                "type": "not_found"}
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM departments WHERE id = %s;", (req.id,))
        conn.commit()
        _manual_audit(conn, req.performed_by, "DELETE", "departments",
                      f"✓ SUCCESS — Deleted department id={req.id}")
        conn.commit()
        return {"ok": True, "message": f"Department id={req.id} deleted successfully"}
    except Exception as e:
        conn.rollback()
        return {"ok": False, "error": str(e)}
    finally:
        cur.close(); conn.close()

# ── Audit Log ─────────────────────────────────────────────────────────
@app.get("/api/audit")
def audit_log():
    conn = admin_conn()
    cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    dsn_user = _parse_dsn(DATABASE_URL).get("user", "postgres")
    excluded = (
        dsn_user, "postgres", "supabase_admin", "authenticator",
        "supabase_auth_admin", "supabase_storage_admin", "dashboard_user",
        "pgbouncer", "anon", "authenticated", "service_role",
        "pgsodium_keyholder", "supabase_replication_admin",
        "supabase_read_only_user", "supabase_etl_admin"
    )
    try:
        cur.execute("""
            SELECT username, action, table_name, detail,
                   executed_at AT TIME ZONE 'Asia/Karachi' AS ts
            FROM audit_log
            WHERE username NOT IN %s
              AND action IN ('SELECT','INSERT','UPDATE','DELETE')
            ORDER BY executed_at DESC LIMIT 200;
        """, (excluded,))
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        return []
    finally:
        cur.close(); conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("admin_panel:app", host="0.0.0.0", port=8000, reload=True)