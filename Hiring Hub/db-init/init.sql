-- The schema mirrors backend/cv_analyzer/db.py.
-- PostgreSQL runs this file only when the database volume is initialized.

CREATE TABLE organizations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL UNIQUE,
    api_key VARCHAR(100) NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_organizations_api_key ON organizations (api_key);

CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    custom_fields JSON NOT NULL DEFAULT '[]'::json,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_positions_org_title UNIQUE (org_id, title)
);

CREATE INDEX ix_positions_org_id ON positions (org_id);

CREATE TABLE cv_documents (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    position_id INTEGER REFERENCES positions(id) ON DELETE SET NULL,
    original_filename VARCHAR(500) NOT NULL,
    stored_path VARCHAR(1000) NOT NULL,
    file_hash VARCHAR(64) NOT NULL,
    page_count INTEGER,
    file_created_at TIMESTAMP,
    file_modified_at TIMESTAMP,
    pdf_created_at TIMESTAMP,
    pdf_modified_at TIMESTAMP,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error TEXT,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    CONSTRAINT uq_cv_documents_org_position_hash UNIQUE (org_id, position_id, file_hash)
);

CREATE INDEX ix_cv_documents_org_id ON cv_documents (org_id);
CREATE INDEX ix_cv_documents_position_id ON cv_documents (position_id);
CREATE INDEX ix_cv_documents_file_hash ON cv_documents (file_hash);
CREATE INDEX ix_cv_documents_status ON cv_documents (status);

CREATE TABLE candidate_profiles (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL UNIQUE REFERENCES cv_documents(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL,
    position_id INTEGER,
    full_name VARCHAR(300),
    email VARCHAR(300),
    phone VARCHAR(100),
    location VARCHAR(300),
    country VARCHAR(100),
    current_job_title VARCHAR(300),
    career_level VARCHAR(50),
    total_years_experience DOUBLE PRECISION,
    highest_education_level VARCHAR(50),
    num_jobs INTEGER NOT NULL DEFAULT 0,
    num_short_tenures INTEGER NOT NULL DEFAULT 0,
    avg_tenure_months DOUBLE PRECISION,
    worked_multiple_countries BOOLEAN NOT NULL DEFAULT FALSE,
    contact_complete BOOLEAN NOT NULL DEFAULT FALSE,
    years_since_graduation INTEGER,
    cv_language VARCHAR(50),
    job_categories JSON NOT NULL DEFAULT '[]'::json,
    industry_sectors JSON NOT NULL DEFAULT '[]'::json,
    companies JSON NOT NULL DEFAULT '[]'::json,
    technical_skills JSON NOT NULL DEFAULT '[]'::json,
    soft_skills JSON NOT NULL DEFAULT '[]'::json,
    software_and_tools JSON NOT NULL DEFAULT '[]'::json,
    languages JSON NOT NULL DEFAULT '[]'::json,
    countries_worked JSON NOT NULL DEFAULT '[]'::json,
    key_takeaways JSON NOT NULL DEFAULT '[]'::json,
    additional_info JSON NOT NULL DEFAULT '[]'::json,
    custom_fields JSON NOT NULL DEFAULT '[]'::json,
    data JSON NOT NULL,
    derived JSON NOT NULL,
    model VARCHAR(100),
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_candidate_profiles_org_id ON candidate_profiles (org_id);
CREATE INDEX ix_candidate_profiles_position_id ON candidate_profiles (position_id);
CREATE INDEX ix_candidate_profiles_email ON candidate_profiles (email);

CREATE TABLE candidate_skills (
    id SERIAL PRIMARY KEY,
    profile_id INTEGER NOT NULL REFERENCES candidate_profiles(id) ON DELETE CASCADE,
    org_id INTEGER NOT NULL,
    skill VARCHAR(200) NOT NULL,
    skill_normalized VARCHAR(200) NOT NULL,
    skill_type VARCHAR(30) NOT NULL
);

CREATE INDEX ix_candidate_skills_profile_id ON candidate_skills (profile_id);
CREATE INDEX ix_skill_org_name ON candidate_skills (org_id, skill_normalized);

CREATE TABLE chat_sessions (
    id SERIAL PRIMARY KEY,
    org_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    position_id INTEGER NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
    messages JSON NOT NULL DEFAULT '[]'::json,
    current_candidate_ids JSON NOT NULL DEFAULT '[]'::json,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_chat_sessions_org_position UNIQUE (org_id, position_id)
);

CREATE INDEX ix_chat_sessions_org_id ON chat_sessions (org_id);
CREATE INDEX ix_chat_sessions_position_id ON chat_sessions (position_id);
