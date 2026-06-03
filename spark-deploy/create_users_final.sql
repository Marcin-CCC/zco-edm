-- Create users in the database
-- Passwords: admin123, password1, password2
INSERT INTO users (username, email, full_name, role, hashed_password, is_active, created_at, updated_at)
VALUES (
    'admin',
    'admin@zco.szczecin.pl',
    'Administrator Systemu',
    'ADMIN',
    '$2b$12$JVW0WkDXaoXN/DXT9hCc9eXGwbASucAmxLOTpQZ8Bqn0DMBHb2Kkq',
    TRUE,
    NOW(),
    NOW()
)
ON CONFLICT (username) DO UPDATE
SET email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    hashed_password = EXCLUDED.hashed_password,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

INSERT INTO users (username, email, full_name, role, hashed_password, is_active, created_at, updated_at)
VALUES (
    'user1',
    'user1@zco.szczecin.pl',
    'Jan Kowalski',
    'DOCTOR',
    '$2b$12$ORqCgmHIf1DBaZYMbG1XtOcjfA.IyTPIvQ/rWt/DEuar3Y9Ywr6Mu',
    TRUE,
    NOW(),
    NOW()
)
ON CONFLICT (username) DO UPDATE
SET email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    hashed_password = EXCLUDED.hashed_password,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

INSERT INTO users (username, email, full_name, role, hashed_password, is_active, created_at, updated_at)
VALUES (
    'user2',
    'user2@zco.szczecin.pl',
    'Anna Nowak',
    'MEDICAL_STAFF',
    '$2b$12$Ky1d4Nj9hMWHQO9KULlSFOVTDg9n2eHG9nrO/95n8LVoWzkaqFlmG',
    TRUE,
    NOW(),
    NOW()
)
ON CONFLICT (username) DO UPDATE
SET email = EXCLUDED.email,
    full_name = EXCLUDED.full_name,
    role = EXCLUDED.role,
    hashed_password = EXCLUDED.hashed_password,
    is_active = EXCLUDED.is_active,
    updated_at = NOW();

-- Create default folders
INSERT INTO folders (name, path, created_by) VALUES
    ('/dokumenty-medyczne', '/dokumenty-medyczne', 1),
    ('/raporty-biurowe', '/raporty-biurowe', 1),
    ('/raporty-otrieczone', '/raporty-otrieczone', 1)
ON CONFLICT (path) DO NOTHING;

-- Verify
SELECT id, username, email, role, is_active FROM users ORDER BY id;
SELECT id, name, path FROM folders ORDER BY id;