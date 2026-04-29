DROP TABLE IF EXISTS "MessageHidden" CASCADE;
DROP TABLE IF EXISTS "Message" CASCADE;
DROP TABLE IF EXISTS "ChannelMember" CASCADE;
DROP TABLE IF EXISTS "Channel" CASCADE;
DROP TABLE IF EXISTS "WorkspaceMember" CASCADE;
DROP TABLE IF EXISTS "Workspace" CASCADE;
DROP TABLE IF EXISTS "User" CASCADE;

CREATE TABLE "User" (
    uid SERIAL PRIMARY KEY,
    email text NOT NULL UNIQUE,
    username text NOT NULL UNIQUE,
    nickname text,
    password text NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE "Workspace" (
    wid SERIAL PRIMARY KEY,
    name text NOT NULL,
    description text,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER NOT NULL,
    CONSTRAINT fk_workspace_creator FOREIGN KEY (created_by) REFERENCES "User" (uid) ON DELETE RESTRICT
);

CREATE TABLE "WorkspaceMember" (
    wmid SERIAL PRIMARY KEY,
    uid INTEGER NOT NULL,
    wid INTEGER NOT NULL,
    invited_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ,
    role TEXT CHECK (role IN ('admin','member')) NOT NULL DEFAULT 'member',
    CONSTRAINT fk_wm_user FOREIGN KEY (uid) REFERENCES "User"(uid) ON DELETE CASCADE,
    CONSTRAINT fk_wm_workspace FOREIGN KEY (wid) REFERENCES "Workspace"(wid) ON DELETE CASCADE,
    CONSTRAINT uq_wm UNIQUE (uid, wid),
    CONSTRAINT chk_wm_join_implies_invited CHECK (joined_at IS NULL OR invited_at IS NOT NULL)
);

CREATE TABLE "Channel" (
    name TEXT NOT NULL,
    wid INTEGER NOT NULL,
    type TEXT CHECK (type IN ('public','private','direct')) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER NOT NULL,
    PRIMARY KEY (name, wid),
    CONSTRAINT fk_channel_workspace FOREIGN KEY (wid) REFERENCES "Workspace"(wid) ON DELETE CASCADE,
    CONSTRAINT fk_channel_creator FOREIGN KEY (created_by) REFERENCES "User"(uid) ON DELETE RESTRICT
);

CREATE TABLE "ChannelMember" (
    cmid SERIAL PRIMARY KEY,
    wmid INTEGER NOT NULL,
    channel_name TEXT NOT NULL,
    channel_wid INTEGER NOT NULL,
    invited_at TIMESTAMPTZ,
    joined_at TIMESTAMPTZ,
    CONSTRAINT fk_cm_wm FOREIGN KEY (wmid) REFERENCES "WorkspaceMember"(wmid) ON DELETE CASCADE,
    CONSTRAINT fk_cm_channel FOREIGN KEY (channel_name, channel_wid) REFERENCES "Channel"(name, wid) ON DELETE CASCADE,
    CONSTRAINT uq_cm UNIQUE (wmid, channel_name, channel_wid),
    CONSTRAINT chk_cm_join_implies_invited CHECK (joined_at IS NULL OR invited_at IS NOT NULL)
);

CREATE TABLE "Message" (
    mid SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channel_name TEXT NOT NULL,
    channel_wid INTEGER NOT NULL,
    cmid INTEGER NOT NULL,
    is_recalled BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_msg_channel FOREIGN KEY (channel_name, channel_wid) REFERENCES "Channel"(name, wid) ON DELETE CASCADE,
    CONSTRAINT fk_msg_sender FOREIGN KEY (cmid) REFERENCES "ChannelMember"(cmid) ON DELETE CASCADE
);

CREATE TABLE "MessageHidden" (
    mid INTEGER NOT NULL,
    uid INTEGER NOT NULL,
    hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mid, uid),
    CONSTRAINT fk_mh_message FOREIGN KEY (mid) REFERENCES "Message" (mid) ON DELETE CASCADE,
    CONSTRAINT fk_mh_user FOREIGN KEY (uid) REFERENCES "User" (uid) ON DELETE CASCADE
);

INSERT INTO "User" (uid, email, username, nickname, password, created_at) VALUES
(1, 'a@test.com', 'alice', 'Alice', 'pass', NOW()),
(2, 'b@test.com', 'bob', 'Bob', 'pass', NOW()),
(3, 'c@test.com', 'charlie', 'Charlie', 'pass', NOW()),
(4, 'd@test.com', 'dexton', 'Dexton', 'pass', NOW()),
(5, 'e@test.com', 'eric', 'Eric', 'pass', NOW());

INSERT INTO "Workspace" (wid, name, description, created_at, created_by) VALUES
(1, 'Company', 'Main workspace', NOW(), 1),
(2, 'Dev Team', 'Development workspace', NOW(), 2);

INSERT INTO "WorkspaceMember" (wmid, uid, wid, invited_at, joined_at, role) VALUES
(1, 1, 1, NOW(), NOW(), 'admin'),
(2, 2, 1, NOW(), NOW(), 'admin'),
(3, 3, 1, NOW(), NOW(), 'member'),
(4, 2, 2, NOW(), NOW(), 'admin'),
(5, 4, 2, NOW(), NOW(), 'member'),
(6, 5, 1, NOW() - INTERVAL '3 days', NULL, 'member'),
(7, 5, 2, NOW() - INTERVAL '1 day', NULL, 'member');

INSERT INTO "Channel" (name, wid, type, created_at, created_by) VALUES
('general', 1, 'public', NOW(), 1),
('random', 1, 'public', NOW(), 1),
('leadership', 1, 'private', NOW(), 1),
('dev', 2, 'public', NOW(), 2);

INSERT INTO "ChannelMember" (cmid, wmid, channel_name, channel_wid, invited_at, joined_at) VALUES
(1, 1, 'general', 1, NOW(), NOW()),
(2, 2, 'general', 1, NOW(), NOW()),
(3, 3, 'general', 1, NOW(), NOW()),
(4, 1, 'random', 1, NOW(), NOW()),
(5, 2, 'random', 1, NOW(), NOW()),
(6, 1, 'leadership', 1, NOW(), NOW()),
(7, 4, 'dev', 2, NOW(), NOW()),
(8, 5, 'dev', 2, NOW(), NOW()),
(9, 3, 'leadership', 1, NOW() - INTERVAL '2 days', NULL);

INSERT INTO "Message" (mid, content, sent_at, channel_name, channel_wid, cmid, is_recalled, is_deleted) VALUES
(1, 'Welcome to #general!', NOW(), 'general', 1, 1, FALSE, FALSE),
(2, 'Thanks Alice! Excited to be here.', NOW(), 'general', 1, 2, FALSE, FALSE),
(3, 'Same here — hello everyone.', NOW(), 'general', 1, 3, FALSE, FALSE),
(4, 'Anyone up for coffee this week?', NOW(), 'random', 1, 5, FALSE, FALSE),
(5, 'Shipped the auth fix to staging.', NOW(), 'dev', 2, 7, FALSE, FALSE),
(6, 'Nice, I will review the PR this afternoon.', NOW(), 'dev', 2, 8, FALSE, FALSE);

-- Keep SERIAL sequences aligned after explicit IDs (safe for re-runs / more inserts)
SELECT setval(pg_get_serial_sequence('"User"', 'uid'), (SELECT COALESCE(MAX(uid), 1) FROM "User"));
SELECT setval(pg_get_serial_sequence('"Workspace"', 'wid'), (SELECT COALESCE(MAX(wid), 1) FROM "Workspace"));
SELECT setval(pg_get_serial_sequence('"WorkspaceMember"', 'wmid'), (SELECT COALESCE(MAX(wmid), 1) FROM "WorkspaceMember"));
SELECT setval(pg_get_serial_sequence('"ChannelMember"', 'cmid'), (SELECT COALESCE(MAX(cmid), 1) FROM "ChannelMember"));
SELECT setval(pg_get_serial_sequence('"Message"', 'mid'), (SELECT COALESCE(MAX(mid), 1) FROM "Message"));
