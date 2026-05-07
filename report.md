# Snickr — Project Report
### CS-GY 6083 · Database Systems

---

## 1. What Is This System

**Snickr** is a web-based team messaging application modelled after real-time collaboration tools such as Slack. It allows users to register accounts, create shared workspaces, organise conversations into typed channels (public, private, or direct), and exchange messages within those channels. The system is multi-tenant: a single deployment serves any number of independent workspaces, each with its own member list, roles, and channel structure.

Key capabilities include:

- **User accounts** — registration, login/logout, profile editing, password change, and account deletion with ownership-transfer safeguards.
- **Workspaces** — creation, invitation-based membership, role management (`admin` / `member`), and ownership transfer.
- **Channels** — public (open to all workspace members), private (invite-only with explicit acceptance), and direct (1-to-1 between two workspace members).
- **Messaging** — chat system within joined channels, message recall (permanently hidden for all users within 2 minutes of sending), sender-only message deletion (hides the message only for the sender), and cross-channel search.

---

## 2. System Design

### 2.1 Entity–Relationship Diagram

The ER diagram for Snickr is shown below.

![ER Diagram](/assets/proj2.png)

### 2.2 Relational Schema, Keys & Foreign Key Constraints

The six core relations and the supplementary `MessageHidden` relation are summarised below. Underlined attributes form the primary key of each relation.

| Relation | Primary Key | Notable Attributes |
|---|---|---|
| **User** | <u>uid</u> | email, username, nickname, password, created_at |
| **Workspace** | <u>wid</u> | name, description, created_at, created_by |
| **WorkspaceMember** | <u>wmid</u> | uid, wid, invited_at, joined_at, role |
| **Channel** | <u>name, wid</u> | type, created_at, created_by |
| **ChannelMember** | <u>cmid</u> | wmid, channel_name, channel_wid, invited_at, joined_at |
| **Message** | <u>mid</u> | content, sent_at, channel_name, channel_wid, cmid, is_recalled, is_deleted |
| **MessageHidden** | <u>mid, uid</u> | hidden_at |

**Foreign key constraints:**

- `Workspace.created_by` → `User.uid` (`ON DELETE RESTRICT`)
- `WorkspaceMember.uid` → `User.uid` (`ON DELETE CASCADE`)
- `WorkspaceMember.wid` → `Workspace.wid` (`ON DELETE CASCADE`)
- `Channel.wid` → `Workspace.wid` (`ON DELETE CASCADE`)
- `Channel.created_by` → `User.uid` (`ON DELETE RESTRICT`)
- `ChannelMember.wmid` → `WorkspaceMember.wmid` (`ON DELETE CASCADE`)
- `ChannelMember.(channel_name, channel_wid)` → `Channel.(name, wid)` (`ON DELETE CASCADE`)
- `Message.(channel_name, channel_wid)` → `Channel.(name, wid)` (`ON DELETE CASCADE`)
- `Message.cmid` → `ChannelMember.cmid` (`ON DELETE CASCADE`)
- `MessageHidden.mid` → `Message.mid` (`ON DELETE CASCADE`)
- `MessageHidden.uid` → `User.uid` (`ON DELETE CASCADE`)

### 2.3 Relational Database Schema (SQL)

```sql
CREATE TABLE "User" (
    uid        SERIAL PRIMARY KEY,
    email      TEXT NOT NULL UNIQUE,
    username   TEXT NOT NULL UNIQUE,
    nickname   TEXT,
    password   TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE "Workspace" (
    wid         SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by  INTEGER NOT NULL,
    CONSTRAINT fk_workspace_creator
        FOREIGN KEY (created_by) REFERENCES "User"(uid) ON DELETE RESTRICT
);

CREATE TABLE "WorkspaceMember" (
    wmid       SERIAL PRIMARY KEY,
    uid        INTEGER NOT NULL,
    wid        INTEGER NOT NULL,
    invited_at TIMESTAMPTZ,
    joined_at  TIMESTAMPTZ,
    role       TEXT NOT NULL DEFAULT 'member'
                   CHECK (role IN ('admin', 'member')),
    CONSTRAINT fk_wm_user
        FOREIGN KEY (uid) REFERENCES "User"(uid) ON DELETE CASCADE,
    CONSTRAINT fk_wm_workspace
        FOREIGN KEY (wid) REFERENCES "Workspace"(wid) ON DELETE CASCADE,
    CONSTRAINT uq_wm UNIQUE (uid, wid),
    CONSTRAINT chk_wm_join_implies_invited
        CHECK (joined_at IS NULL OR invited_at IS NOT NULL)
);

CREATE TABLE "Channel" (
    name       TEXT        NOT NULL,
    wid        INTEGER     NOT NULL,
    type       TEXT        NOT NULL CHECK (type IN ('public', 'private', 'direct')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by INTEGER     NOT NULL,
    PRIMARY KEY (name, wid),
    CONSTRAINT fk_channel_workspace
        FOREIGN KEY (wid) REFERENCES "Workspace"(wid) ON DELETE CASCADE,
    CONSTRAINT fk_channel_creator
        FOREIGN KEY (created_by) REFERENCES "User"(uid) ON DELETE RESTRICT
);

CREATE TABLE "ChannelMember" (
    cmid         SERIAL PRIMARY KEY,
    wmid         INTEGER NOT NULL,
    channel_name TEXT    NOT NULL,
    channel_wid  INTEGER NOT NULL,
    invited_at   TIMESTAMPTZ,
    joined_at    TIMESTAMPTZ,
    CONSTRAINT fk_cm_wm
        FOREIGN KEY (wmid) REFERENCES "WorkspaceMember"(wmid) ON DELETE CASCADE,
    CONSTRAINT fk_cm_channel
        FOREIGN KEY (channel_name, channel_wid)
        REFERENCES "Channel"(name, wid) ON DELETE CASCADE,
    CONSTRAINT uq_cm UNIQUE (wmid, channel_name, channel_wid),
    CONSTRAINT chk_cm_join_implies_invited
        CHECK (joined_at IS NULL OR invited_at IS NOT NULL)
);

CREATE TABLE "Message" (
    mid          SERIAL PRIMARY KEY,
    content      TEXT        NOT NULL,
    sent_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    channel_name TEXT        NOT NULL,
    channel_wid  INTEGER     NOT NULL,
    cmid         INTEGER     NOT NULL,
    is_recalled  BOOLEAN     NOT NULL DEFAULT FALSE,
    is_deleted   BOOLEAN     NOT NULL DEFAULT FALSE,
    CONSTRAINT fk_msg_channel
        FOREIGN KEY (channel_name, channel_wid)
        REFERENCES "Channel"(name, wid) ON DELETE CASCADE,
    CONSTRAINT fk_msg_sender
        FOREIGN KEY (cmid) REFERENCES "ChannelMember"(cmid) ON DELETE CASCADE
);

CREATE TABLE "MessageHidden" (
    mid       INTEGER     NOT NULL,
    uid       INTEGER     NOT NULL,
    hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (mid, uid),
    CONSTRAINT fk_mh_message
        FOREIGN KEY (mid) REFERENCES "Message"(mid) ON DELETE CASCADE,
    CONSTRAINT fk_mh_user
        FOREIGN KEY (uid) REFERENCES "User"(uid) ON DELETE CASCADE
);
```

### 2.4 Design Justifications

**User** is a standalone regular entity. We assume email and username must each be unique across the entire system, so both are declared `UNIQUE` at the schema level, which prevents duplicate accounts without any additional application-layer check.

**Workspace** stores `created_by` as a foreign key to `User` directly in the relation, translated from the `created_by` relationship in the ER diagram. The creator implicitly holds an administrator role, captured via their `WorkspaceMember` entry with `role = 'admin'`. The FK on `created_by` uses `ON DELETE RESTRICT`: the application must reassign `created_by` to another user before issuing the account deletion; once no references remain, the delete proceeds. This ensures workspaces, channels, and messages are preserved when a creator leaves.

**WorkspaceMember** is a regular entity with surrogate primary key `wmid` rather than a weak entity. While it could theoretically be modelled as a weak entity dependent on `User` and `Workspace`, there is no natural discriminator to distinguish multiple memberships for the same user–workspace pair, so a system-generated key is cleaner and more practical for referencing in downstream tables. The `role` attribute captures administrator versus regular member status. A `NULL` value in `joined_at` indicates a pending invitation that has not yet been accepted. The FK on `uid` uses `ON DELETE CASCADE`: when a user account is deleted, their workspace memberships are removed automatically, which in turn cascades to `ChannelMember` and `Message` rows. The FK on `wid` also uses `ON DELETE CASCADE`: deleting a workspace removes all its member records.

**Channel** is a weak entity dependent on `Workspace` via its identifying relationship. Its discriminator is `name`, meaning channel names must be unique within a workspace but not globally. The composite primary key `(name, wid)` reflects this. The `type` attribute explicitly stores whether a channel is `public`, `private`, or `direct`, making queries simpler and more efficient than inferring type from membership counts at runtime. `created_by` stores the UID of the creating user directly. The FK on `created_by` uses `ON DELETE RESTRICT` for the same reason as `Workspace`: ownership must be transferred before the creator's account can be deleted. The FK on `wid` uses `ON DELETE CASCADE`: deleting a workspace removes all its channels.

**ChannelMember** is a regular entity with surrogate primary key `cmid`. It references `wmid` rather than `uid` directly, enforcing at the schema level that only current workspace members can be channel members. A `NULL` in `joined_at` indicates a pending invitation.

**Message** is a regular entity with surrogate primary key `mid`, globally unique across all channels. It references `(channel_name, channel_wid)` to record which channel the message belongs to, and `cmid` to record which channel member sent it. The two boolean flags `is_recalled` and `is_deleted` support soft-state operations: a recalled message replaces its content with a placeholder string rather than being physically removed, allowing the UI to communicate that a message existed.

**MessageHidden** is a supplementary relation that implements per-user message hiding. When a user chooses to hide a message, a row `(mid, uid)` is inserted with the current timestamp. The hidden message is filtered out in queries for that specific user but remains visible to all other channel members; its content is never physically altered. The composite primary key `(mid, uid)` ensures each user can hide any given message at most once. Both foreign keys use `ON DELETE CASCADE`: if a message is hard-deleted, or if the hiding user's account is removed, the corresponding `MessageHidden` records are automatically cleaned up.

### 2.5 Assumptions

1. **Nickname display.** A nickname is a display name for a user and does not need to be unique. Once set, it is used across all workspaces and channels the user belongs to. If a user has not set a nickname, their `username` is used for display purposes instead.

2. **Administrator privileges.** Only the creator of a workspace can promote or demote other members between `admin` and `member` roles; administrators cannot grant admin status to others. This is enforced by checking `Workspace.created_by`. A non-creator administrator cannot remove the workspace creator. Administrators can otherwise perform all creator-level operations: inviting workspace members, creating channels, and removing non-creator members.

3. **Explicit channel type.** Channel `type` is stored explicitly as an attribute on `Channel` with values `public`, `private`, or `direct`. This simplifies queries significantly compared to inferring type from membership counts at runtime.

4. **Workspace membership required for channel membership.** Only workspace members can be channel members. `ChannelMember` references `WorkspaceMember` rather than `User` directly, enforcing this constraint at the schema level.

5. **Message deletion on member removal.** Messages are deleted if the sending `ChannelMember` record is removed. Because `Message.cmid` references `ChannelMember.cmid` with `ON DELETE CASCADE`, removing a channel member also removes their messages. This cascades further on account deletion: deleting a `User` row cascades to `WorkspaceMember`, then to `ChannelMember`, then to `Message`. Deleted users' message history is not preserved.

6. **Plain text messages.** Message content is stored and displayed as plain text.

7. **UTC timestamps.** All timestamps are stored as `TIMESTAMPTZ` (UTC with timezone information) for consistency across time zones.

8. **At most one active membership.** At any given time a user has at most one active membership in a workspace or channel (i.e., where `joined_at` is not `NULL` and the record has not been removed). This is enforced at the application level, complemented by the `UNIQUE (uid, wid)` constraint on `WorkspaceMember` and `UNIQUE (wmid, channel_name, channel_wid)` on `ChannelMember`.

9. **Ownership transfer required before account deletion.** A user who is the creator (`created_by`) of any `Workspace` or `Channel` cannot delete their account until they have transferred ownership of those resources to another active member. This is enforced at the database level via `ON DELETE RESTRICT` on `Workspace.created_by` and `Channel.created_by`. Once ownership is transferred, the account deletion proceeds and the cascade on `WorkspaceMember.uid` automatically removes their memberships, channel memberships, and messages.

10. **Channel visibility for non-members.** A user can only view the messages in a channel if they are a joined member of that channel. Even workspace administrators cannot read channel messages unless they have joined the channel. Administrators are only granted the ability to delete a channel without being a member. Furthermore, when workspace ownership is transferred, the new owner inherits only the channels whose `created_by` field is updated to them; they do not automatically inherit membership in any channel the previous owner was a member of. Full channel access still requires an explicit invitation and acceptance.

---

## 3. Technology Stack & Data Flow

### 3.1 Technology Stack

| Layer | Technology | Notes |
|---|---|---|
| **Web framework** | Python 3.12 · Flask | Handles HTTP routing, server-side rendering, and session management |
| **Database** | PostgreSQL 18 | Relational storage; accessed via `psycopg2` |
| **Database driver** | psycopg2 | Low-level Python adapter; used for all SQL execution |
| **Templating** | Jinja2 (bundled with Flask) | Server-side HTML rendering; templates live in `templates/` |
| **Static assets** | Plain CSS + vanilla JavaScript | Served from `static/`; no client-side framework |
| **Application server** | Gunicorn | WSGI server; 2 workers × 2 threads per container |
| **Containerisation** | Docker · Docker Compose | One container for the Flask app, one for PostgreSQL |
| **Deployment** | Railway (optional) | Cloud hosting target; SSL and `DATABASE_URL` injected as env vars |

### 3.2 Data Flow

Snickr uses a conventional synchronous request–response model. A typical HTTP request–response cycle proceeds as follows:

1. **Browser → Flask.** The user's browser sends an HTTP request (GET or POST) to the Gunicorn/Flask server. POST requests carry form data in the request body.
2. **Session check.** Flask reads the signed session cookie (see §3.4) to identify the logged-in user. If the cookie is absent or invalid, the user is redirected to `/login`.
3. **Route handler.** The matching Flask route function opens a `psycopg2` connection to PostgreSQL, executes one or more parameterised SQL queries (see §3.3), and closes the connection in a `finally` block.
4. **Template rendering.** Query results are passed to a Jinja2 template. Jinja2 auto-escapes all variables rendered into HTML (see §3.5), producing a complete HTML page.
5. **Response → Browser.** Flask returns the rendered HTML with appropriate HTTP headers, including the `Content-Security-Policy` header added by the `_apply_security_headers` after-request hook.

### 3.3 Defence Against SQL Injection

All database queries are executed using **parameterised statements** via the psycopg2 `%s` placeholder syntax. User-supplied values — form fields, URL parameters, session values — are **never interpolated directly into SQL strings**. Instead, they are passed as a separate tuple to `cursor.execute()`, and the psycopg2 driver sends the query and parameters independently to PostgreSQL. This guarantees that user input is always treated as a data value and can never be interpreted as SQL syntax, eliminating the SQL injection attack surface entirely. For example:

```python
cur.execute(
    'SELECT uid, nickname FROM "User" WHERE email = %s AND password = %s',
    (email, password),
)
```

### 3.4 Session Cookies & User Authentication

User identity is maintained via Flask's **server-side signed session cookie**. On successful login the server stores the user's `uid` (and display nickname) in `flask.session`, which Flask serialises and signs using an `itsdangerous` HMAC with the application `SECRET_KEY`. The resulting opaque token is sent to the browser as a cookie. On every subsequent request Flask verifies the signature and deserialises the session; if the signature does not match, the session is treated as empty.

The cookie is configured with the following security attributes:

| Attribute | Value | Purpose |
|---|---|---|
| `HttpOnly` | `True` (Flask default) | Prevents JavaScript from reading the session cookie, mitigating XSS-based session theft |
| `Secure` | `True` when running on Railway (HTTPS) | Instructs the browser to send the cookie only over TLS connections |
| `SameSite` | `Lax` (default) | Prevents the cookie from being sent on cross-site requests initiated by third-party pages, mitigating CSRF |

### 3.5 Defence Against Cross-Site Scripting (XSS)

Two complementary mechanisms protect against XSS:

1. **Jinja2 auto-escaping.** All variables rendered into HTML templates via `{{ variable }}` are HTML-escaped by Jinja2 by default. Characters such as `<`, `>`, `"`, `'`, and `&` in user-supplied content are converted to their HTML entity equivalents, so a message like `<script>alert(1)</script>` is rendered as literal text rather than executed.

2. **Content-Security-Policy (CSP) header.** Every HTML response carries a `Content-Security-Policy` header assembled by `_content_security_policy()`. The policy restricts the origins from which scripts, styles, images, fonts, and connections may be loaded:
   - `default-src 'self'` — blocks loading of any resource from an external origin by default.
   - `script-src 'self' 'unsafe-inline'` — permits only same-origin scripts and inline `<script>` blocks (required by the current template design).
   - `frame-ancestors 'none'` — prevents the app from being embedded in an iframe (clickjacking defence).
   - `object-src 'none'` — blocks Flash and plugin-based injection vectors.
   - `form-action 'self'` — forms may only submit to the same origin.

---

## 4. How To Use The System

### 4.1 Getting Started

There are two ways to access Snickr: via the live deployed instance or by running the application locally with Docker Compose.

---

**Option A — Deployed instance (recommended):**

Visit the live application at:

> **`https://cs-gy-6083-project-production.up.railway.app`**

No installation is required. You can register a new account immediately and begin using the system. All data is persisted in the cloud-hosted PostgreSQL database.

---

**Option B — Running locally with Docker Compose:**

Prerequisites: [Docker Desktop](https://www.docker.com/products/docker-desktop/) must be installed and running.

```bash
# 1. Clone the repository and navigate to its root
git clone https://github.com/ccczy-czy/CS-GY-6083-Project
cd CS-GY-6083-Project

# 2. Build the image and start both services (PostgreSQL + Flask app)
docker compose up --build

# 3. Open http://localhost:5000 in a browser

# 4. Stop with Ctrl+C; to wipe the database volume entirely:
docker compose down -v
```

The local instance connects to a containerised PostgreSQL database that is initialised automatically from `schema.sql` on first start. Data persists in the named Docker volume between restarts unless `docker compose down -v` is used.

### 4.2 Registration and Login

Navigate to the application root (the deployed URL or `http://localhost:5000` for a local instance). You will be redirected to `/login`. Click **Register** to create an account, providing a unique email address, a unique username, an optional nickname, and a password. After registration you are redirected to the login page. Enter your email and password to log in. To log out, click the **Logout** link available on any authenticated page.

### 4.3 Workspaces

After logging in you land on the **Home** page (`/home`), which lists:
- All workspaces you have **joined**, with a link to each workspace's detail page.
- Any **pending workspace invitations** you have received (with Accept / Decline buttons).

**Creating a workspace:** Click **Create Workspace**, enter a name and optional description. You are automatically added as an `admin` member.

**Workspace detail page** (`/workspace/<wid>`): Shows all channels in the workspace and, for admin members, the full member list including pending invitees.

**Inviting members (admins only):** From the workspace detail page, enter the invitee's email address. The invited user receives a pending invitation visible on their Home page.

**Role management (workspace creator only):** The creator can promote any `member` to `admin` or demote any `admin` (other than themselves) back to `member`.

**Removing members (admins only):** Admins can remove any non-creator member. Removal cascades to that user's channel memberships and messages within the workspace.

**Transferring workspace ownership:** The creator can transfer the `created_by` field to another active member from the **Profile** page (`/profile`). This is required before the creator can delete their account.

### 4.4 Channels

From the workspace detail page:

**Creating a channel:** Enter a name and select a type:
- **Public** — visible and joinable by any workspace member.
- **Private** — requires an explicit invitation from the channel creator or a workspace admin; invitees must accept before they can chat.
- **Direct** — a 1-to-1 channel; select one other workspace member as the counterpart.

**Joining public channels:** Click **Join** next to any listed public channel.

**Accepting private channel invitations:** Navigate to **Pending Invitations** (`/invitations`) to accept or decline private channel invites.

**Deleting a channel (workspace admins only):** Admins can delete any channel from the workspace detail page, regardless of whether they are a member of that channel.

### 4.5 Messaging

**Chat view** (`/chat/<wid>/<channel_name>`): The main interface shows the message history for the current channel on the right and a sidebar listing all channels you can see across your workspaces on the left.

**Sending a message:** Type in the input box at the bottom and press Enter or click **Send**.

**Recalling a message:** Within **2 minutes** of sending, you can recall your own message. Once recalled, the message is hidden for all users - no other channel member can see the original content.

**Deleting a message:** Click the **Delete** action on any of your own messages to hide it from your view only. The deletion is recorded by inserting a row into `MessageHidden` keyed on `(mid, uid)`; the message remains fully visible to all other channel members.

**Searching messages:** Navigate to `/search`, enter a keyword, and the system returns matching messages from channels you have joined, with a link to the relevant channel.

### 4.6 Profile and Account Management

Navigate to `/profile` to:
- **Edit** your email, username, and nickname (each field is validated for uniqueness and format).
- **Change your password** (requires current password for confirmation).
- **Transfer workspace ownership** (required before deleting your account if you own workspaces).
- **Delete your account** (requires password confirmation; blocked if you still own any workspace or channel).

---

## 5. Session Logs (see session_logs.txt for full SQL logs)

> 1. **Registration and login** — a new user registers, logs in, and views their empty Home page.
![Register](/assets/register.png)
![Login](/assets/login.png)
![Home](/assets/fresh_home.png)
> 2. **Workspace creation and member invitation** — a user creates a workspace, invites another user by email, and the invitee accepts the pending invitation.
![Create Workspace](/assets/create_workspace.png)
![After Create Workspace](/assets/after_create_workspace.png)
![Invite To Workspace](/assets/invite_to_workspace.png)
![View Invitation](/assets/view_workspace_invitation.png)
![Joined Workspace](/assets/joined_workspace.png)
![View Workspace](/assets/view_workspace_after_member_join.png)
> 3. **Channel creation and messaging** — an admin creates a public channel, a member joins it, and the two users exchange messages in the Chat view.
![Create Public Channel](/assets/create_public_channel.png)
![View Channels](/assets/view_channels.png)
![Joined Public](/assets/joined_public.png)
![Exchange Messages](/assets/exchange_messages.png)
> 4. **Private channel invite flow** — admin invites a member to a private channel; the member navigates to Pending Invitations and accepts; the member can now see and send messages.
![Create Private Channel](/assets/create_private_channel.png)
![View Channels](/assets/view_channels_2.png)
![Invite Private](/assets/invite_private.png)
![View Channel](/assets/view_channel.png)
![View Channel Invitation](/assets/view_workspace_invitation.png)
![View Channels](/assets/view_channels_3.png)
> 5. **Message recall and delete** — a user recalls one of their own messages within the 2-minute window (hidden for all) and deletes another of their own messages (hidden for themselves only); both effects are visible in the chat view.
![Pre-recall](/assets/pre_recall.png)
![After Recall](/assets/after_recall.png)
![After Recall 2](/assets/after_recall_2.png)
![Pre-delete](/assets/pre_delete.png)
![After Delete](/assets/after_delete.png)
![After Delete 2](/assets/after_delete_2.png)
> 6. **Account deletion with ownership transfer** — the workspace creator transfers ownership to another member via the Profile page, then successfully deletes their account.
![Delete Account](/assets/delete_account.png)
![Transferred Ownership](/assets/transfer_ownership.png)
