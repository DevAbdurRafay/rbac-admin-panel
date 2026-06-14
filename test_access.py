import psycopg2
from dotenv import load_dotenv
import os
import re

load_dotenv()

BASE  = os.getenv("DATABASE_URL")
match = re.match(r"postgresql://[^:]+:[^@]+@([^/]+)/(\w+)", BASE)
HOST   = match.group(1)
DBNAME = match.group(2)

USERS = {
    "hr_user":      "hr@2026#Secure",
    "sales_user":   "sales@2024#Secure",
    "rd_user":      "rd@2024#Secure",
    "manager_user": "manager@2024#Secure",
}

TESTS = {
    "hr_user": [
        ("SELECT", "SELECT * FROM employees LIMIT 1;",                        True),
        ("INSERT", "INSERT INTO departments (dept_name) VALUES ('TestDept');", True),
        ("DELETE", "DELETE FROM employees WHERE emp_id = 9999;",              False),
    ],
    "sales_user": [
        ("SELECT", "SELECT * FROM employees LIMIT 1;",                         True),
        ("INSERT", "INSERT INTO departments (dept_name) VALUES ('TestDept2');", False),
        ("UPDATE", "UPDATE employees SET age = 30 WHERE emp_id = 1;",          False),
    ],
    "rd_user": [
        ("SELECT", "SELECT * FROM employees LIMIT 1;",                True),
        ("UPDATE", "UPDATE employees SET age = 25 WHERE emp_id = 1;", True),
        ("DELETE", "DELETE FROM employees WHERE emp_id = 9999;",      False),
    ],
    "manager_user": [
        ("SELECT salary_records", "SELECT * FROM salary_records LIMIT 1;",     True),
        ("INSERT",                "INSERT INTO employees (job_role) VALUES ('Test');", False),
        ("DELETE",                "DELETE FROM salary_records WHERE record_id = 9999;", False),
    ],
}

print("=" * 60)
print("  DB ACCESS CONTROL TEST")
print("=" * 60)

for username, password in USERS.items():
    print(f"\n--- {username.upper()} ---")
    try:
        conn = psycopg2.connect(
            host=HOST,
            dbname=DBNAME,
            user=username,
            password=password,
            sslmode="require"
        )
        conn.autocommit = False

        for op, sql, should_pass in TESTS.get(username, []):
            try:
                cur = conn.cursor()
                cur.execute(sql)
                conn.rollback()
                status = "PASS" if should_pass else "UNEXPECTED PASS"
                icon   = "✓" if should_pass else "!"
                print(f"  {icon} {op:30s} → {status}")
            except psycopg2.errors.InsufficientPrivilege:
                conn.rollback()
                status = "PASS (blocked)" if not should_pass else "FAIL (should have access)"
                icon   = "✓" if not should_pass else "✗"
                print(f"  {icon} {op:30s} → {status}")
            except Exception as e:
                conn.rollback()
                print(f"  ? {op:30s} → ERROR: {e}")

        conn.close()
    except Exception as e:
        print(f"  Could not connect: {e}")

print("\n" + "=" * 60)
print("  TEST COMPLETE")
print("=" * 60)