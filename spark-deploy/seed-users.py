#!/usr/bin/env python3
"""Seed users into the database on Spark."""
import subprocess

sql = """
-- Create users
INSERT INTO users (username, email, full_name, role, hashed_password, is_active, last_login)
VALUES (
    'admin',
    'admin@zco.szczecin.pl',
    'Administrator Systemu',
    'admin',
    '$2b$12$DSqFtHv3ytjdj.71EdWk/Omxn25orM0xAzMB0/2LvPhXA5NozCbFW',
    TRUE,
    CURRENT_TIMESTAMP
)
ON CONFLICT (username) DO UPDATE
SET email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    hashed_password = EXCLUDED.hashed_password,
    is_active = EXCLUDED.is_active;

INSERT INTO users (username, email, full_name, role, hashed_password, is_active)
VALUES (
    'user1',
    'user1@zco.szczecin.pl',
    'Jan Kowalski',
    'doctor',
    '$2b$12$x8t1cyaI82BGJkqM382zSuQ6dlx5dpSjl9xoPSS81MDxl9qf.1KuG',
    TRUE
)
ON CONFLICT (username) DO UPDATE
SET email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    hashed_password = EXCLUDED.hashed_password,
    is_active = EXCLUDED.is_active;

INSERT INTO users (username, email, full_name, role, hashed_password, is_active)
VALUES (
    'user2',
    'user2@zco.szczecin.pl',
    'Anna Nowak',
    'medical_staff',
    '$2b$12$GCblKla56y0NIKEYf2V6sOFk4ubV992Fg6hc4JF4WTgCDmk3v9b0K',
    TRUE
)
ON CONFLICT (username) DO UPDATE
SET email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    hashed_password = EXCLUDED.hashed_password,
    is_active = EXCLUDED.is_active;

-- Create default folders (created by admin, id=1)
INSERT INTO folders (name, path, created_by) VALUES
    ('/dokumenty-medyczne', '/dokumenty-medyczne', 1),
    ('/raporty-biurowe', '/raporty-biurowe', 1),
    ('/raporty-otrieczone', '/raporty-otrieczone', 1)
ON CONFLICT (path) DO NOTHING;

SELECT id, email, role, is_active FROM users ORDER BY id;
SELECT id, name, path FROM folders ORDER BY id;
"""

# Write SQL to a temp file on Spark
result = subprocess.run(
    ['ssh', 'spark', 'python3', '-c', f'''
import sys
sql = sys.stdin.read()
with open("/tmp/seed-users.sql", "w") as f:
    f.write(sql)
print("SQL written")
'''],
    input=sql, capture_output=True, text=True
)
print("STDIN:", result.stdout, result.stderr)

# Run the SQL
result2 = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', 'edm-zco-postgres', 'psql', '-U', 'postgres', '-d', 'edmdatabase', '-f', '/tmp/seed-users.sql'],
    capture_output=True, text=True
)
print("STDOUT:", result2.stdout[:2000])
if result2.stderr:
    print("STDERR:", result2.stderr[:500])

# Verify
result3 = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', 'edm-zco-postgres', 'psql', '-U', 'postgres', '-d', 'edmdatabase', '-t', '-c', 'SELECT id, email, role, is_active FROM users ORDER BY id;'],
    capture_output=True, text=True
)
print("USERS:", result3.stdout)