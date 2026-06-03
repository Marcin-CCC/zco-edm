#!/usr/bin/env python3
"""Check and create users on Spark."""
import subprocess, os

# Step 1: Copy the create users script to the backend container
script_content = r'''from app.database import SessionLocal
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

db.commit()
users = db.query(User).filter(User.is_active == True).all()
for u in users:
    print(f"User: id={u.id}, email={u.email}, role={u.role.value}")
db.close()
print("Done")
'''

# Write to local temp
with open('/tmp/_create_users.py', 'w') as f:
    f.write(script_content)

# Copy to Spark
print("Copying to Spark...")
result1 = subprocess.run(['scp', '/tmp/_create_users.py', 'spark:/tmp/_create_users.py'], capture_output=True, text=True)
print("scp:", result1.stderr)

# Copy into container
print("Copying into container...")
result2 = subprocess.run(['ssh', 'spark', 'docker', 'cp', '/tmp/_create_users.py', 'edm-backend-spark:/app/_create_users.py'], capture_output=True, text=True)
print("docker cp:", result2.stderr)

# Verify file exists in container
result3 = subprocess.run(['ssh', 'spark', 'docker', 'exec', 'edm-backend-spark', 'ls', '-la', '/app/_create_users.py'], capture_output=True, text=True)
print("ls:", result3.stdout, result3.stderr)

# Run inside container with PYTHONPATH
print("Running...")
result4 = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', 'edm-backend-spark', 'sh', '-c', 'cd /app && PYTHONPATH=/app python3 /app/_create_users.py'],
    capture_output=True, text=True
)
print("\nCREATE RESULT:")
print("STDOUT:", result4.stdout)
print("STDERR:", result4.stderr)

# Verify users
result5 = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', 'edm-backend-spark', 'sh', '-c', 'cd /app && PYTHONPATH=/app python3 -c "from app.database import SessionLocal; from app.models import User; db=SessionLocal(); [print(f\\\"id={x.id} email={x.email} role={x.role.value}\\\") for x in db.query(User).all()]; db.close()"'],
    capture_output=True, text=True
)
print("\nVERIFY:")
print("STDOUT:", result5.stdout)
print("STDERR:", result5.stderr)