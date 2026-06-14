import psycopg2, os
from dotenv import load_dotenv

load_dotenv()
URL = os.getenv("DATABASE_URL")

def run():
    conn = psycopg2.connect(URL)
    conn.autocommit = False
    cur  = conn.cursor()

    print("── Creating tables ──")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id                        SERIAL PRIMARY KEY,
        emp_id                    VARCHAR(20) UNIQUE,
        age                       INT,
        age_group                 VARCHAR(20),
        attrition                 VARCHAR(5),
        business_travel           VARCHAR(40),
        daily_rate                INT,
        department                VARCHAR(60),
        distance_from_home        INT,
        education                 INT,
        education_field           VARCHAR(50),
        employee_number           INT,
        environment_satisfaction  INT,
        gender                    VARCHAR(10),
        hourly_rate               INT,
        job_involvement           INT,
        job_level                 INT,
        job_role                  VARCHAR(60),
        job_satisfaction          INT,
        marital_status            VARCHAR(20),
        monthly_income            NUMERIC(10,2),
        salary_slab               VARCHAR(20),
        monthly_rate              INT,
        num_companies_worked      INT,
        overtime                  VARCHAR(5),
        percent_salary_hike       INT,
        performance_rating        INT,
        relationship_satisfaction INT,
        standard_hours            INT,
        stock_option_level        INT,
        total_working_years       INT,
        training_times_last_year  INT,
        work_life_balance         INT,
        years_at_company          INT,
        years_in_current_role     INT,
        years_since_last_promotion INT,
        years_with_curr_manager   INT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id        SERIAL PRIMARY KEY,
        dept_name VARCHAR(60) UNIQUE NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS salary_records (
        id             SERIAL PRIMARY KEY,
        emp_id         VARCHAR(20) REFERENCES employees(emp_id) ON DELETE CASCADE,
        monthly_income NUMERIC(10,2),
        salary_slab    VARCHAR(20),
        percent_hike   INT,
        recorded_on    DATE DEFAULT CURRENT_DATE
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
        id          SERIAL PRIMARY KEY,
        username    VARCHAR(60),
        action      VARCHAR(20),
        table_name  VARCHAR(60),
        record_id   VARCHAR(40),
        detail      TEXT,
        executed_at TIMESTAMPTZ DEFAULT NOW()
    );
    """)

    print("── Creating roles (no users) ──")
    roles = [
        "hr_manager_role",         # HR: full employee & dept control
        "finance_analyst_role",    # Finance: salary & compensation data
        "it_admin_role",           # IT: schema/access management support
        "workforce_analyst_role",  # Monitoring & Analysis: read-only, reporting
    ]
    for r in roles:
        cur.execute(f"""
            DO $$ BEGIN CREATE ROLE {r};
            EXCEPTION WHEN duplicate_object THEN NULL; END $$;
        """)

    print("── Setting role privileges ──")

    # HR Manager — full control over employee records and departments
    cur.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON employees,departments TO hr_manager_role;")
    cur.execute("GRANT SELECT ON salary_records TO hr_manager_role;")
    cur.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO hr_manager_role;")

    # Finance Analyst — salary records full access, employee/dept read-only
    cur.execute("GRANT SELECT ON employees,departments TO finance_analyst_role;")
    cur.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON salary_records TO finance_analyst_role;")
    cur.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO finance_analyst_role;")

    # IT Admin — read access across all tables for troubleshooting & support
    cur.execute("GRANT SELECT ON employees,departments,salary_records,audit_log TO it_admin_role;")
    cur.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO it_admin_role;")

    # Workforce Analyst — read-only on everything for dashboards & analysis
    cur.execute("GRANT SELECT ON employees,departments,salary_records TO workforce_analyst_role;")

    # All roles can write to audit_log
    cur.execute("""
        GRANT INSERT ON audit_log TO
            hr_manager_role, finance_analyst_role, it_admin_role, workforce_analyst_role;
    """)
    cur.execute("""
        GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO
            hr_manager_role, finance_analyst_role, it_admin_role, workforce_analyst_role;
    """)
    cur.execute("""
        GRANT USAGE, SELECT, UPDATE ON SEQUENCE audit_log_id_seq TO
            hr_manager_role, finance_analyst_role, it_admin_role, workforce_analyst_role;
    """)

    print("── Creating audit trigger function ──")
    cur.execute("""
    CREATE OR REPLACE FUNCTION log_audit()
    RETURNS TRIGGER AS $$
    DECLARE
        app_user TEXT;
    BEGIN
        app_user := COALESCE(NULLIF(current_setting('app.current_user', true), ''), session_user);

        IF TG_OP = 'INSERT' THEN
            INSERT INTO audit_log(username, action, table_name, record_id, detail, executed_at)
            VALUES (
                app_user, 'INSERT', TG_TABLE_NAME,
                CAST(NEW.id AS VARCHAR),
                'Inserted: ' || row_to_json(NEW)::TEXT,
                NOW()
            );
            RETURN NEW;

        ELSIF TG_OP = 'UPDATE' THEN
            INSERT INTO audit_log(username, action, table_name, record_id, detail, executed_at)
            VALUES (
                app_user, 'UPDATE', TG_TABLE_NAME,
                CAST(NEW.id AS VARCHAR),
                'Before: ' || row_to_json(OLD)::TEXT || ' | After: ' || row_to_json(NEW)::TEXT,
                NOW()
            );
            RETURN NEW;

        ELSIF TG_OP = 'DELETE' THEN
            INSERT INTO audit_log(username, action, table_name, record_id, detail, executed_at)
            VALUES (
                app_user, 'DELETE', TG_TABLE_NAME,
                CAST(OLD.id AS VARCHAR),
                'Deleted: ' || row_to_json(OLD)::TEXT,
                NOW()
            );
            RETURN OLD;
        END IF;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    print("── Attaching triggers to tables ──")
    for tbl in ['employees', 'departments', 'salary_records']:
        cur.execute(f"""
            DROP TRIGGER IF EXISTS audit_{tbl}_trigger ON {tbl};
        """)
        cur.execute(f"""
            CREATE TRIGGER audit_{tbl}_trigger
            AFTER INSERT OR UPDATE OR DELETE ON {tbl}
            FOR EACH ROW EXECUTE FUNCTION log_audit();
        """)
    print("✓ Triggers attached to employees, departments, salary_records")

    conn.commit()
    cur.close()
    conn.close()
    print("\n✓ Tables + roles ready.")
    print("✓ No Users created — use admin panel to create users and assign roles.")
    print("Next: python load_data.py")

if __name__ == "__main__":
    run()