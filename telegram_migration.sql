-- Add telegram_chat_id to existing profiles table
ALTER TABLE profiles
  ADD COLUMN IF NOT EXISTS telegram_chat_id TEXT UNIQUE;

-- Fast lookup index (used every time a message arrives)
CREATE INDEX IF NOT EXISTS idx_profiles_telegram_chat_id
  ON profiles (telegram_chat_id);
