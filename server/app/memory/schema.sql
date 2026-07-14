-- ════════════════════════════════════════════════════════════════════
--  Схема Supabase для памяти ассистента: лица (pgvector) + сессии
--  Выполнить в Supabase → SQL Editor один раз.
-- ════════════════════════════════════════════════════════════════════

create extension if not exists vector;

-- Пациенты. embedding — вектор лица от InsightFace buffalo_l (512 dim).
create table if not exists patients (
    id           uuid primary key default gen_random_uuid(),
    name         text,
    phone        text,
    embedding    vector(512),
    notes        text,                      -- контекст: аллергии, предпочтения
    created_at   timestamptz not null default now(),
    last_seen_at timestamptz
);

-- ANN-индекс по косинусной близости для быстрого поиска «узнали ли лицо».
create index if not exists patients_embedding_idx
    on patients using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- Сессии — один визит пациента (для логики «не здороваться повторно»).
create table if not exists sessions (
    id          uuid primary key default gen_random_uuid(),
    patient_id  uuid references patients(id) on delete set null,
    started_at  timestamptz not null default now(),
    ended_at    timestamptz,
    greeted     boolean not null default false,
    summary     text                        -- о чём говорили (краткое резюме)
);

-- Реплики — полный лог разговора.
create table if not exists interactions (
    id          bigserial primary key,
    session_id  uuid references sessions(id) on delete cascade,
    role        text not null,              -- 'user' | 'assistant'
    content     text not null,
    created_at  timestamptz not null default now()
);

create index if not exists interactions_session_idx on interactions(session_id);

-- RPC: найти ближайшего пациента по эмбеддингу лица.
-- Возвращает id/name и дистанцию (0 — идентично, 2 — противоположно).
create or replace function match_patient(query_embedding vector(512))
returns table (id uuid, name text, distance float)
language sql stable as $$
    select p.id, p.name, (p.embedding <=> query_embedding) as distance
    from patients p
    where p.embedding is not null
    order by p.embedding <=> query_embedding
    limit 1;
$$;
