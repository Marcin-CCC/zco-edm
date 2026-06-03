#!/usr/bin/env python3
"""Check if users exist in the database."""
import subprocess

# Check users
result = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', '-w', '/app', 'edm-backend-spark', 'python', '-c',
     'from app.database import SessionLocal\nfrom app.models import User\ndb=SessionLocal()\nu=db.query(User).all()\nprint(f"Total users: {len(u)}")\n[print(f"id={x.id} email={x.email} role={x.role.value}") for x in u]\ndb.close()'],
    capture_output=True, text=True
)
print("QUERY RESULT:")
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)

# If no users, create them
if 'Total users: 0' in result.stdout:
    print("\nNo users found. Creating users...")
    
    script = r'''
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
print(f"Done")
'''
    
    # Write script to a temp file on local machine
    with open('/tmp/_create_users.py', 'w') as f:
        f.write(script)
    
    # Copy to Spark temp, then to container
    subprocess.run(['scp', '/tmp/_create_users.py', 'spark:/tmp/_create_users.py'])
    subprocess.run(['ssh', 'spark', 'docker', 'cp', '/tmp/_create_users.py', 'edm-backend-spark:/app/_create_users.py'])
    
    # Run inside container
    result2 = subprocess.run(
        ['ssh', 'spark', 'docker', 'exec', '-i', '-w', '/app', 'edm-backend-spark', 'PYTHONPATH=/app', 'python', '/app/_create_users.py'],
        capture_output=True, text=True
    )
    print("\nCREATE RESULT:")
    print("STDOUT:", result2.stdout)
    print("STDERR:", result2.stderr)
else:
    print("Users already exist!")