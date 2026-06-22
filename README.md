<h1 align="center">RBAC Admin Panel</h1>

<p>
A <strong>FastAPI-based Role-Based Access Control (RBAC)</strong> system built with <strong>PostgreSQL (Supabase)</strong>.  
It provides secure authentication, role management, permission control, and a protected SQL execution engine with full audit logging.
</p>

<h2>🚀 Features</h2>

<ul>
  <li>Role-Based Access Control (RBAC)</li>
  <li>User Management (Create, Delete, Assign Roles)</li>
  <li>Secure SQL Engine (Only SELECT, INSERT, UPDATE, DELETE allowed)</li>
  <li>Blocks dangerous queries (DROP, ALTER, GRANT, etc.)</li>
  <li>Admin Dashboard APIs (Stats, Health, System Info)</li>
  <li>Full Audit Logging System</li>
  <li>Employees, Departments & Salary Management</li>
</ul>

---

<h2>🛠️ Tech Stack</h2>

<p>
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Supabase-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" />
  <img src="https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white" alt="HTML5" />
  <img src="https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white" alt="CSS3" />
  <img src="https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black" alt="JavaScript" />
</p>

---

<h2>🏗️ Architecture</h2>

<ul>
  <li><strong>API Layer:</strong> FastAPI REST APIs</li>
  <li><strong>Database Layer:</strong> PostgreSQL (Supabase)</li>
  <li><strong>Security Layer:</strong> RBAC Permission Engine</li>
  <li><strong>Audit Layer:</strong> Activity Logging System</li>
</ul>

---

<h2>⚙️ Setup & Installation</h2>

<pre><code>
git clone https://github.com/DevAbdurRafay/rbac-admin-panel.git
cd rbac-admin-panel
pip install -r requirements.txt
uvicorn main:app --reload
</code></pre>

---

<h2>📂 Project Structure</h2>
<ul>
 <li><code>admin_panel.py</code> - FastAPI application entry point</li>
 <li><code>db_setup.py</code> - Supabase connection setup</li>
 <li><code>templates/</code> - UI pages (HTML templates for admin dashboard)</li>
 <li><code>static/</code> - CSS assets and frontend styling files</li>
 <li><code>.env.example</code> - Sample environment variables file for configuration setup</li>  
</ul>

---

<p align="center">
  <em>Developed as part of an university lab project.</em>
</p>
