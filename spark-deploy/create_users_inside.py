#!/usr/bin/env python3
"""Create users inside the backend container."""
import subprocess, pathlib

# Copy the script into the backend container
subprocess.run(['ssh', 'spark', 'docker', 'cp', '/tmp/_create_users_on_spark.py', 'edm-backend-spark:/app/_create_users_on_spark.py'])

# Now write a wrapper script that sets PYTHONPATH and runs
wrapper = r'''#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')
from app.database import SessionLocal
from app.models import User, UserRole
from passlib.context import CryptContext
from datetime import datetime

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
db = SessionLocal()

users_data = [
    {"username": "admin", "email": "admin@zco.szczecin.pl", "full_name": "Administrator Systemu", "role": UserRole.ADMIN, "password": "admin123"},
    {"username": "user1", "email": "user1@zco.szczecin.pl", "full_name": "Jan Kowalski", "role": UserRole.DOCTOR, "password": "password1"},
    {"username": "user2", "email": "user2@zco.szczecin.pl", "full_name": "Anna Nowak", "role": UserRole.MEDICAL_STAFF, "password": "password2"},
]

created = 0
for u in users_data:
    existing = db.query(User).filter(User.email == u["email"]).first()
    if existing:
        existing.username = u["username"]
        existing.full_name = u["full_name"]
        existing.role = u["role"]
        existing.hashed_password = pwd_context.hash(u["password"])
        existing.is_active = True
        existing.updated_at = datetime.utcnow()
    else:
        new_user = User(
            username=u["username"],
            email=u["email"],
            full_name=u["full_name"],
            role=u["role"],
            hashed_password=pwd_context.hash(u["password"]),
            is_active=True,
        )
        db.add(new_user)
    created += 1

db.commit()

users = db.query(User).filter(User.is_active == True).all()
for u in users:
    print(f"User: id={u.id}, email={u.email}, role={u.role.value}")

db.close()
print(f"Created/updated {created} users")
'''

# Write the wrapper to Spark
with open('/tmp/_wrapper.py', 'w') as f:
    f.write(wrapper)

subprocess.run(['scp', '/tmp/_wrapper.py', 'spark:/tmp/_wrapper.py'])
subprocess.run(['ssh', 'spark', 'docker', 'cp', '/tmp/_wrapper.py', 'edm-backend-spark:/app/_wrapper.py'])

# Run inside container
result = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', 'edm-backend-spark', 'python', '/app/_wrapper.py'],
    capture_output=True, text=True
)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)

# Verify
result2 = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', 'edm-backend-spark', 'python', '-c', 'from app.database import SessionLocal; from app.models import User; db=SessionLocal(); [print(f"id={u.id} email={u.email} role={u.role.value}") for u in db.query(User).all()]; db.close()'],
    capture_output=True, text=True
)
print("VERIFY:", result2.stdout)