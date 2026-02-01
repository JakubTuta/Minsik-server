-- ============================================================================
-- Minsik Database Initialization Script
-- ============================================================================
-- This script runs on first PostgreSQL container startup
-- Creates all required schemas for the application
-- Run by docker-entrypoint-initdb.d mechanism
-- ============================================================================

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy string matching

-- ============================================================================
-- Create Schemas
-- ============================================================================

-- Auth schema: Users, refresh tokens, authentication data
CREATE SCHEMA IF NOT EXISTS auth;
COMMENT ON SCHEMA auth IS 'Authentication and user management';

-- Books schema: Books, authors, genres (hybrid model with cover history)
CREATE SCHEMA IF NOT EXISTS books;
COMMENT ON SCHEMA books IS 'Book catalog with hybrid model (one book per language)';

-- User Data schema: Bookshelves, ratings, notes, reading profiles
CREATE SCHEMA IF NOT EXISTS user_data;
COMMENT ON SCHEMA user_data IS 'User-generated content and reading data';

-- Recommendations schema: Similarities, influences, cached recommendations
CREATE SCHEMA IF NOT EXISTS recommendations;
COMMENT ON SCHEMA recommendations IS 'Recommendation engine data and caching';

-- ============================================================================
-- Grant Permissions (if using specific application user)
-- ============================================================================
-- Uncomment and modify if using a separate app user instead of postgres
-- GRANT ALL PRIVILEGES ON SCHEMA auth TO minsik_app;
-- GRANT ALL PRIVILEGES ON SCHEMA books TO minsik_app;
-- GRANT ALL PRIVILEGES ON SCHEMA user_data TO minsik_app;
-- GRANT ALL PRIVILEGES ON SCHEMA recommendations TO minsik_app;

-- ============================================================================
-- Set Search Path (optional, for convenience)
-- ============================================================================
-- ALTER DATABASE minsik_db SET search_path TO books, user_data, recommendations, auth, public;

-- ============================================================================
-- Initialization Complete
-- ============================================================================
-- Tables will be created by Alembic migrations in application code
-- This script only creates the schema structure
-- ============================================================================
