#!/usr/bin/env python3
"""Create users via the backend API."""
import subprocess, json

# Create users via the FastAPI app directly
script = """
from app.main import app
from app.database import SessionLocal
from app.models import User
from passlib.context import CryptContext
from datetime import datetime
import sys

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

db = SessionLocal()

users_data = [
    {"username": "admin", "email": "admin@zco.szczecin.pl", "full_name": "Administrator Systemu", "role": "admin", "password": "admin123"},
    {"username": "user1", "email": "user1@zco.szczecin.pl", "full_name": "Jan Kowalski", "role": "doctor", "password": "password1"},
    {"username": "user2", "email": "user2@zco.szczecin.pl", "full_name": "Anna Nowak", "role": "medical_staff", "password": "password2"},
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
"""

result = subprocess.run(
    ['ssh', 'spark', 'docker', 'exec', '-i', 'edm-backend-spark', 'python', '-c', script],
    capture_output=True, text=True
)
print("STDOUT:", result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[-1000:])