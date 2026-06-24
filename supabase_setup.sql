-- Enable the pgvector extension to work with embedding vectors
create extension if not exists vector;

-- Drop the existing table if you ran this before
drop table if exists documents;

-- Create a table to store your documents
create table documents (
  id bigserial primary key,
  content text, -- corresponds to Document.pageContent
  metadata jsonb, -- corresponds to Document.metadata
  embedding vector(3072), -- 3072 works for Google's gemini-embedding-2
  fts tsvector generated always as (to_tsvector('english', content)) stored
);

create index if not exists documents_fts_idx on documents using gin (fts);

-- Create a function to search for documents
create or replace function match_documents (
  query_embedding vector(3072),
  match_count int DEFAULT null,
  filter jsonb DEFAULT '{}'
) returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language plpgsql
as $$
#variable_conflict use_column
begin
  return query
  select
    id,
    content,
    metadata,
    1 - (documents.embedding <=> query_embedding) as similarity
  from documents
  where metadata @> filter
  order by documents.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- Create profiles table
create table if not exists public.profiles (
  id uuid references auth.users on delete cascade primary key,
  name text not null,
  username text unique not null,
  email text unique not null,
  scholar_id varchar(7) unique not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint scholar_id_format check (scholar_id ~ '^\d{7}$')
);

-- Enable Row Level Security (RLS)
alter table public.profiles enable row level security;

-- Drop existing policies if they exist to avoid duplication errors on run
drop policy if exists "Public profiles are viewable by everyone" on public.profiles;
drop policy if exists "Users can insert their own profile" on public.profiles;
drop policy if exists "Users can update their own profile" on public.profiles;

-- Create RLS policies
create policy "Public profiles are viewable by everyone" on public.profiles
  for select using (true);

create policy "Users can insert their own profile" on public.profiles
  for insert with check (auth.uid() = id);

create policy "Users can update their own profile" on public.profiles
  for update using (auth.uid() = id);

-- Create a trigger function to handle new auth user signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, name, username, email, scholar_id)
  values (
    new.id,
    coalesce(new.raw_user_meta_data->>'name', ''),
    coalesce(new.raw_user_meta_data->>'username', ''),
    new.email,
    coalesce(new.raw_user_meta_data->>'scholar_id', '')
  );
  return new;
end;
$$ language plpgsql security definer;

-- Recreate trigger
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Create chats table
create table if not exists public.chats (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references public.profiles(id) on delete cascade not null,
  title text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Enable RLS for chats
alter table public.chats enable row level security;

-- Create RLS policies for chats
drop policy if exists "Users can view their own chats" on public.chats;
drop policy if exists "Users can insert their own chats" on public.chats;
drop policy if exists "Users can delete their own chats" on public.chats;

create policy "Users can view their own chats" on public.chats
  for select using (auth.uid() = user_id);

create policy "Users can insert their own chats" on public.chats
  for insert with check (auth.uid() = user_id);

create policy "Users can delete their own chats" on public.chats
  for delete using (auth.uid() = user_id);

-- Create messages table
create table if not exists public.messages (
  id uuid default gen_random_uuid() primary key,
  chat_id uuid references public.chats(id) on delete cascade not null,
  role text not null check (role in ('user', 'bot')),
  content text not null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Enable RLS for messages
alter table public.messages enable row level security;

-- Create RLS policies for messages
drop policy if exists "Users can view messages of their chats" on public.messages;
drop policy if exists "Users can insert messages into their chats" on public.messages;

create policy "Users can view messages of their chats" on public.messages
  for select using (
    exists (
      select 1 from public.chats
      where chats.id = messages.chat_id and chats.user_id = auth.uid()
    )
  );

create policy "Users can insert messages into their chats" on public.messages
  for insert with check (
    exists (
      select 1 from public.chats
      where chats.id = messages.chat_id and chats.user_id = auth.uid()
    )
  );

-- Create a function to perform Hybrid Search with RRF (Reciprocal Rank Fusion)
create or replace function hybrid_search(
  query_text text,
  query_embedding vector(3072),
  match_count int,
  filter jsonb DEFAULT '{}',
  full_text_weight float default 1.0,
  semantic_weight float default 1.0,
  rrf_k int default 50
)
returns table (
  id bigint,
  content text,
  metadata jsonb,
  similarity float
)
language sql
as $$
with full_text as (
  select
    d.id,
    row_number() over(order by ts_rank_cd(d.fts, websearch_to_tsquery('english', query_text)) desc) as rank_ix
  from
    documents d
  where
    d.fts @@ websearch_to_tsquery('english', query_text)
    and d.metadata @> filter
),
semantic as (
  select
    d.id,
    row_number() over (order by d.embedding <=> query_embedding) as rank_ix
  from
    documents d
  where
    d.metadata @> filter
)
select
  documents.id,
  documents.content,
  documents.metadata,
  (coalesce(1.0 / (rrf_k + full_text.rank_ix), 0.0) * full_text_weight +
   coalesce(1.0 / (rrf_k + semantic.rank_ix), 0.0) * semantic_weight) as similarity
from
  full_text
  full outer join semantic
    on full_text.id = semantic.id
  join documents
    on coalesce(full_text.id, semantic.id) = documents.id
order by similarity desc
limit match_count;
$$;
