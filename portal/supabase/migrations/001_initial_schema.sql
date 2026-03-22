-- GKE Upgrades Skill Feedback Portal Schema
-- Run this in your Supabase SQL Editor to set up the database

-- ============================================================
-- Invite Codes table
-- ============================================================
CREATE TABLE IF NOT EXISTS invite_codes (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  code TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL DEFAULT 'reviewer' CHECK (role IN ('reviewer', 'admin')),
  max_uses INTEGER,
  uses INTEGER DEFAULT 0,
  active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Create initial admin invite code
INSERT INTO invite_codes (code, role, max_uses, active)
VALUES ('GKE-ADMIN-2026', 'admin', 5, true)
ON CONFLICT (code) DO NOTHING;

-- Create initial reviewer invite code
INSERT INTO invite_codes (code, role, max_uses, active)
VALUES ('GKE-REVIEW-2026', 'reviewer', 50, true)
ON CONFLICT (code) DO NOTHING;

-- ============================================================
-- Feedback table
-- ============================================================
CREATE TABLE IF NOT EXISTS feedback (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('correction', 'missing', 'improvement', 'new_eval', 'kb_update')),
  topic TEXT NOT NULL,
  eval_id INTEGER,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  current_behavior TEXT,
  expected_behavior TEXT,
  source TEXT,
  priority TEXT DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
  submitted_by TEXT NOT NULL,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'incorporated')),
  reviewed_by TEXT,
  reviewed_at TIMESTAMPTZ,
  admin_notes TEXT,
  iteration_id INTEGER,  -- which iteration this feedback was incorporated into
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_feedback_status ON feedback(status);
CREATE INDEX IF NOT EXISTS idx_feedback_type ON feedback(type);
CREATE INDEX IF NOT EXISTS idx_feedback_submitted_by ON feedback(submitted_by);

-- ============================================================
-- Iterations table (tracks eval runs)
-- ============================================================
CREATE TABLE IF NOT EXISTS iterations (
  id SERIAL PRIMARY KEY,
  iteration_number INTEGER NOT NULL UNIQUE,
  status TEXT DEFAULT 'draft' CHECK (status IN ('draft', 'running', 'complete')),
  claude_with_skill REAL,
  claude_without_skill REAL,
  claude_delta REAL,
  gemini_with_skill REAL,
  gemini_without_skill REAL,
  gemini_delta REAL,
  total_evals INTEGER,
  total_assertions INTEGER,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Seed iteration history
INSERT INTO iterations (iteration_number, status, claude_with_skill, claude_without_skill, claude_delta, total_evals, total_assertions, notes)
VALUES
  (4, 'complete', 0.804, 0.711, 0.093, 23, 194, 'Initial'),
  (5, 'complete', 0.835, 0.558, 0.277, 37, 310, 'AI/ML evals added'),
  (6, 'complete', 0.826, 0.568, 0.258, 37, 310, 'Rollout sequence tuning'),
  (7, 'complete', 0.778, 0.509, 0.269, 40, 338, 'PM feedback v1'),
  (8, 'complete', 0.750, 0.497, 0.253, 40, 340, 'KB consumed, run 1'),
  (9, 'complete', 0.779, 0.485, 0.294, 40, 340, 'KB consumed, run 2'),
  (10, 'complete', 0.768, 0.556, 0.212, 40, 340, 'Gemini side-by-side')
ON CONFLICT (iteration_number) DO NOTHING;

-- Update iteration 10 with Gemini data
UPDATE iterations SET
  gemini_with_skill = 0.688,
  gemini_without_skill = 0.518,
  gemini_delta = 0.170
WHERE iteration_number = 10;

-- ============================================================
-- Row Level Security (RLS)
-- ============================================================
-- Enable RLS
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE invite_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE iterations ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read/write for feedback (auth is handled by invite codes at app level)
CREATE POLICY "Allow all feedback operations" ON feedback
  FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all invite_codes operations" ON invite_codes
  FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow all iterations operations" ON iterations
  FOR ALL USING (true) WITH CHECK (true);

-- ============================================================
-- Updated_at trigger
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER feedback_updated_at
  BEFORE UPDATE ON feedback
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
