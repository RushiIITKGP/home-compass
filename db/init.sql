-- Runs automatically the first time the postgres container initializes its
-- data volume (see docker-compose.yml's docker-entrypoint-initdb.d mount).
--
-- Phase 1 adds the actual tables (users, listings, neighborhoods, etc.)
-- via SQLAlchemy models — this file only needs to prepare the extension
-- those models depend on.

CREATE EXTENSION IF NOT EXISTS vector;
