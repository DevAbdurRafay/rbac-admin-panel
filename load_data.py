"""
load_data.py  —  Load HR_Analytics.csv into Supabase PostgreSQL.
Run after db_setup.py.
"""
import pandas as pd, psycopg2, os
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()
URL = os.getenv("DATABASE_URL")

def load():
    print("Reading CSV...")
    df = pd.read_csv("data/HR_Analytics.csv", encoding="utf-8-sig")
    df.columns = df.columns.str.strip()

    conn = psycopg2.connect(URL)
    conn.autocommit = False
    cur  = conn.cursor()

    print("Clearing old data...")
    cur.execute("TRUNCATE salary_records, employees, departments RESTART IDENTITY CASCADE;")

    print("Inserting departments...")
    depts = [(d,) for d in df["Department"].dropna().unique()]
    execute_values(cur,
        "INSERT INTO departments (dept_name) VALUES %s ON CONFLICT DO NOTHING", depts)

    print(f"Inserting {len(df)} employees...")

    def sv(v):
        import math
        if v is None: return None
        try:
            if math.isnan(float(v)): return None
        except: pass
        return v

    rows = []
    for _, r in df.iterrows():
        rows.append((
            sv(r.get("EmpID")),
            sv(r.get("Age")),
            sv(r.get("AgeGroup")),
            sv(r.get("Attrition")),
            sv(r.get("BusinessTravel")),
            sv(r.get("DailyRate")),
            sv(r.get("Department")),
            sv(r.get("DistanceFromHome")),
            sv(r.get("Education")),
            sv(r.get("EducationField")),
            sv(r.get("EmployeeNumber")),
            sv(r.get("EnvironmentSatisfaction")),
            sv(r.get("Gender")),
            sv(r.get("HourlyRate")),
            sv(r.get("JobInvolvement")),
            sv(r.get("JobLevel")),
            sv(r.get("JobRole")),
            sv(r.get("JobSatisfaction")),
            sv(r.get("MaritalStatus")),
            sv(r.get("MonthlyIncome")),
            sv(r.get("SalarySlab")),
            sv(r.get("MonthlyRate")),
            sv(r.get("NumCompaniesWorked")),
            sv(r.get("OverTime")),
            sv(r.get("PercentSalaryHike")),
            sv(r.get("PerformanceRating")),
            sv(r.get("RelationshipSatisfaction")),
            sv(r.get("StandardHours")),
            sv(r.get("StockOptionLevel")),
            sv(r.get("TotalWorkingYears")),
            sv(r.get("TrainingTimesLastYear")),
            sv(r.get("WorkLifeBalance")),
            sv(r.get("YearsAtCompany")),
            sv(r.get("YearsInCurrentRole")),
            sv(r.get("YearsSinceLastPromotion")),
            sv(r.get("YearsWithCurrManager")),
        ))

    execute_values(cur, """
        INSERT INTO employees (
            emp_id, age, age_group, attrition, business_travel, daily_rate,
            department, distance_from_home, education, education_field,
            employee_number, environment_satisfaction, gender, hourly_rate,
            job_involvement, job_level, job_role, job_satisfaction,
            marital_status, monthly_income, salary_slab, monthly_rate,
            num_companies_worked, overtime, percent_salary_hike,
            performance_rating, relationship_satisfaction, standard_hours,
            stock_option_level, total_working_years, training_times_last_year,
            work_life_balance, years_at_company, years_in_current_role,
            years_since_last_promotion, years_with_curr_manager
        ) VALUES %s ON CONFLICT (emp_id) DO NOTHING
    """, rows)

    print("Inserting salary records...")
    cur.execute("SELECT emp_id, monthly_income, salary_slab, percent_salary_hike FROM employees;")
    sal_rows = [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]
    execute_values(cur,
        "INSERT INTO salary_records (emp_id, monthly_income, salary_slab, percent_hike) VALUES %s",
        sal_rows)

    conn.commit()
    cur.close()
    conn.close()
    print(f"\nDone — {len(rows)} employees + {len(sal_rows)} salary records loaded into Supabase.")

if __name__ == "__main__":
    load()