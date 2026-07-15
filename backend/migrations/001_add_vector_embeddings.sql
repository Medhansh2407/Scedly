-- Migration: Add vector embeddings to tasks table
-- Run this on your Supabase SQL Editor (Database → SQL Editor)

-- 1. Enable pgvector extension (already available on Supabase)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Add embedding column to tasks table
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS embedding vector(384);

-- 3. Create index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_tasks_embedding ON tasks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
