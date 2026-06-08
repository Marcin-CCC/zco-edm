-- Seed SQL script - uruchomienie:
--   docker exec -i edm-postgres psql -U postgres -d edmdatabase -f backend/seed.sql
--   lub lokalnie: docker exec -i postgres_rag_container psql -U postgres -d edmdatabase -f seed.sql
--
-- UWAGA: Uzywa usera postgres (z docker-compose.yaml: POSTGRES_USER=postgres, POSTGRES_PASSWORD=tajne_haslo)
-- Hasla userow: admin123, password1, password2 (bcrypt hash wygenerowany przez passlib)

-- ============ TABLES ============

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'guest',
    hashed_password VARCHAR(255) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP WITHOUT TIME ZONE
);

CREATE TABLE IF NOT EXISTS folders (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    path VARCHAR(1000) NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES folders(id),
    created_by INTEGER REFERENCES users(id) NOT NULL,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS folder_permissions (
    id SERIAL PRIMARY KEY,
    folder_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    access_level VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    mime_type VARCHAR(100),
    size BIGINT,
    folder_id INTEGER REFERENCES folders(id),
    uploaded_by INTEGER REFERENCES users(id) NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'W kolejce (n8n)',
    ocr_result TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    folder_path VARCHAR(500),
    mime_type VARCHAR(100),
    file_size INTEGER,
    status VARCHAR(50) DEFAULT 'pending',
    raw_text TEXT,
    error_message TEXT,
    folder_id INTEGER REFERENCES folders(id),
    uploader_id INTEGER REFERENCES users(id),
    chunks_count INTEGER DEFAULT 0,
    vector_id VARCHAR(255),
    upload_date TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP WITHOUT TIME ZONE,
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS document_pages (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER NOT NULL,
    content JSONB,
    raw_content TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS processing_queue (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    started_at TIMESTAMP WITHOUT TIME ZONE,
    completed_at TIMESTAMP WITHOUT TIME ZONE,
    error_message TEXT,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    page_number INTEGER,
    vector_id INTEGER,
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    event_type VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id INTEGER,
    details JSONB,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(100),
    resource_id INTEGER,
    details JSONB,
    ip_address VARCHAR(45),
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ============ INDEXES ============

CREATE INDEX IF NOT EXISTS idx_files_folder_id ON files(folder_id);
CREATE INDEX IF NOT EXISTS idx_files_uploaded_by ON files(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_files_status ON files(status);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_uploader_id ON documents(uploader_id);
CREATE INDEX IF NOT EXISTS idx_documents_folder_id ON documents(folder_id);
CREATE INDEX IF NOT EXISTS idx_processing_queue_status ON processing_queue(status);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log(action);
CREATE INDEX IF NOT EXISTS idx_folders_parent_id ON folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_folder_permissions_folder ON folder_permissions(folder_id);
CREATE INDEX IF NOT EXISTS idx_folder_permissions_user ON folder_permissions(user_id);

-- ============ USERS (with bcrypt hashes) ============
-- Passwords are bcrypt-hashed using passlib:
--   admin123 -> pbkdf2:sha256:260000$...
--   password1 -> pbkdf2:sha256:260000$...
--   password2 -> pbkdf2:sha256:260000$...

-- Insert admin user (password: admin123) - CORRECT BCRYPT HASH
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

-- Insert user1 (password: password1) - CORRECT BCRYPT HASH
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

-- Insert user2 (password: password2) - CORRECT BCRYPT HASH
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

-- ============ DEFAULT FOLDERS ============

-- Create default folders (created by admin, id=1)
INSERT INTO folders (name, path, created_by) VALUES
    ('/dokumenty-medyczne', '/dokumenty-medyczne', 1),
    ('/raporty-biurowe', '/raporty-biurowe', 1),
    ('/raporty-otrieczone', '/raporty-otrieczone', 1)
ON CONFLICT (path) DO NOTHING;

-- ============ DEFAULT FOLDER PERMISSIONS ============

-- Doctors can read all folders
INSERT INTO folder_permissions (folder_id, role, access_level) SELECT f.id, 'doctor', 'read' FROM folders f ON CONFLICT DO NOTHING;

-- Medical staff can read all folders
INSERT INTO folder_permissions (folder_id, role, access_level) SELECT f.id, 'medical_staff', 'read' FROM folders f ON CONFLICT DO NOTHING;

-- Technicians can read all folders
INSERT INTO folder_permissions (folder_id, role, access_level) SELECT f.id, 'technician', 'read' FROM folders f ON CONFLICT DO NOTHING;

-- Office staff can read all folders
INSERT INTO folder_permissions (folder_id, role, access_level) SELECT f.id, 'office_staff', 'read' FROM folders f ON CONFLICT DO NOTHING;

-- Guests can read all folders
INSERT INTO folder_permissions (folder_id, role, access_level) SELECT f.id, 'guest', 'read' FROM folders f ON CONFLICT DO NOTHING;

-- Admin can write to all folders
INSERT INTO folder_permissions (folder_id, role, access_level) SELECT f.id, 'admin', 'write' FROM folders f ON CONFLICT DO NOTHING;

-- ============ SETTINGS TABLE ============

CREATE TABLE IF NOT EXISTS settings (
    key VARCHAR(255) PRIMARY KEY,
    value TEXT NOT NULL DEFAULT '',
    description VARCHAR(500),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Default n8n webhook URL
INSERT INTO settings (key, value, description) VALUES
    ('n8n_webhook_url', 'http://192.168.1.34:5678/webhook/document-uploaded', 'N8N webhook URL for file processing')
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    updated_at = CURRENT_TIMESTAMP;