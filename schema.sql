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
    CONSTRAINT uq_wm UNIQUE (uid, wid)
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
    CONSTRAINT uq_cm UNIQUE (wmid, channel_name, channel_wid)
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