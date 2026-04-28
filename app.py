from __future__ import annotations

import os
from datetime import datetime, timezone
from urllib.parse import quote, unquote

import psycopg2
from flask import Flask, render_template, request, redirect, session, url_for
from psycopg2 import errors

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "shubo_secret_key")


def _prepare_database_url(url: str) -> str:
    """Normalize Heroku/Railway style URLs and require SSL when running on Railway."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if "sslmode=" not in url and os.environ.get("RAILWAY_ENVIRONMENT"):
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


def get_db():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        return psycopg2.connect(_prepare_database_url(database_url))
    return psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        database=os.environ.get("DB_NAME", "Project Part 1"),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "postpre"),
        port=int(os.environ.get("DB_PORT", "5432")),
    )


def _require_user_id() -> int | None:
    uid = session.get("user_id")
    if uid is None:
        return None
    return int(uid)


def is_workspace_admin(cursor, uid: int, wid: int) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM workspacemember
        WHERE wid = %s AND uid = %s AND joined_at IS NOT NULL AND role = 'admin'
        """,
        (wid, uid),
    )
    return cursor.fetchone() is not None


def get_wmid_for_user_in_workspace(cursor, uid: int, wid: int):
    cursor.execute(
        """
        SELECT wmid FROM workspacemember
        WHERE uid = %s AND wid = %s AND joined_at IS NOT NULL
        """,
        (uid, wid),
    )
    row = cursor.fetchone()
    return row[0] if row else None


def user_is_workspace_member(cursor, uid: int, wid: int) -> bool:
    return get_wmid_for_user_in_workspace(cursor, uid, wid) is not None


def user_sent_message(cursor, mid: int, uid: int) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM message m
        JOIN channelmember cm ON m.cmid = cm.cmid
        JOIN workspacemember wm ON cm.wmid = wm.wmid
        WHERE m.mid = %s AND wm.uid = %s
        """,
        (mid, uid),
    )
    return cursor.fetchone() is not None


def can_manage_channel_invites(cursor, uid: int, channel_wid: int, channel_name: str) -> bool:
    """Channel creator or workspace admin may invite to a private channel."""
    if is_workspace_admin(cursor, uid, channel_wid):
        return True
    cursor.execute(
        """
        SELECT 1 FROM channel
        WHERE name = %s AND wid = %s AND created_by = %s
        """,
        (channel_name, channel_wid, uid),
    )
    return cursor.fetchone() is not None


# ----- Routes -----


@app.route("/")
def index():
    return redirect("/home")


@app.route("/users")
def users():
    if "user_id" not in session:
        return redirect("/login")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT uid, nickname FROM \"User\" ORDER BY uid;")
    data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("users.html", users=data)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        username = request.form["username"]
        nickname = request.form["nickname"]
        password = request.form["password"]
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO "User" (email, username, nickname, password)
                VALUES (%s, %s, %s, %s)
                """,
                (email, username, nickname, password),
            )
            conn.commit()
            return redirect("/login")
        except errors.UniqueViolation:
            conn.rollback()
            return render_template(
                "register.html", error="Username or Email already exists"
            )
        except Exception as e:  # noqa: BLE001 — surface DB errors for debugging
            conn.rollback()
            return render_template("register.html", error=str(e))
        finally:
            cur.close()
            conn.close()
    return render_template("register.html")


@app.route("/user/delete/<int:user_id>")
def delete_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM "User" WHERE uid = %s', (user_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/users")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT uid, nickname
            FROM "User"
            WHERE email = %s AND password = %s
            """,
            (email, password),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            session["user_id"] = user[0]
            session["nickname"] = user[1]
            return redirect("/home")
        return render_template("login.html", error="Invalid email or password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


def _load_sidebar_channels(cur, uid: int):
    """Channels the user may see in the sidebar: public in joined WSp, private/direct per rules."""
    cur.execute(
        """
        SELECT c.wid, c.name, c.type, w.name AS wname,
               EXISTS (
                   SELECT 1 FROM channelmember cm2
                   JOIN workspacemember wm2 ON cm2.wmid = wm2.wmid
                   WHERE cm2.channel_wid = c.wid
                     AND cm2.channel_name = c.name
                     AND wm2.uid = %s
                     AND wm2.wid = c.wid
                     AND cm2.joined_at IS NOT NULL
               ) AS is_joined
        FROM channel c
        JOIN workspace w ON c.wid = w.wid
        JOIN workspacemember wm ON wm.wid = w.wid
            AND wm.uid = %s AND wm.joined_at IS NOT NULL
        WHERE
            c.type = 'public'
            OR (c.type = 'private' AND EXISTS (
                SELECT 1 FROM channelmember cm3
                JOIN workspacemember wmx ON cm3.wmid = wmx.wmid
                WHERE cm3.channel_wid = c.wid
                  AND cm3.channel_name = c.name
                  AND wmx.uid = %s
            ))
            OR (c.type = 'direct' AND EXISTS (
                SELECT 1 FROM channelmember cm3
                JOIN workspacemember wmx ON cm3.wmid = wmx.wmid
                WHERE cm3.channel_wid = c.wid
                  AND cm3.channel_name = c.name
                  AND wmx.uid = %s
                  AND cm3.joined_at IS NOT NULL
            ))
        ORDER BY w.name, c.name
        """,
        (uid, uid, uid, uid),
    )
    return cur.fetchall()


@app.route("/home")
def home():
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])

    channel_wid = request.args.get("channel_wid", type=int)
    channel_name = request.args.get("channel_name", type=str)
    if channel_name:
        channel_name = unquote(channel_name)

    conn = get_db()
    cur = conn.cursor()
    channels = _load_sidebar_channels(cur, uid)

    current_channel = None
    messages = []
    if channel_wid and channel_name:
        cur.execute(
            """
            SELECT 1
            FROM channel ch
            JOIN workspacemember wm ON ch.wid = wm.wid
            WHERE ch.wid = %s AND ch.name = %s
              AND wm.uid = %s AND wm.joined_at IS NOT NULL
            """,
            (channel_wid, channel_name, uid),
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return "Not a member of this workspace or invalid channel", 403

        cur.execute(
            """
            SELECT 1
            FROM channel ch
            JOIN channelmember cm ON ch.name = cm.channel_name AND ch.wid = cm.channel_wid
            JOIN workspacemember wm ON cm.wmid = wm.wmid
            WHERE ch.wid = %s AND ch.name = %s AND wm.uid = %s
              AND cm.joined_at IS NOT NULL
            """,
            (channel_wid, channel_name, uid),
        )
        if not cur.fetchone():
            cur.close()
            conn.close()
            return (
                "You must join this channel (public) or accept a pending invite (Invitations page) first.",
                403,
            )

        current_channel = channel_name
        cur.execute(
            """
            SELECT m.mid, m.content, u.nickname, m.sent_at,
                CASE
                    WHEN m.sent_at > NOW() - INTERVAL '2 minutes' THEN TRUE
                    ELSE FALSE
                END AS can_recall
            FROM message m
            JOIN channelmember cm ON m.cmid = cm.cmid
            JOIN workspacemember wm ON cm.wmid = wm.wmid
            JOIN "User" u ON wm.uid = u.uid
            LEFT JOIN message_hidden mh ON m.mid = mh.mid AND mh.uid = %s
            WHERE m.channel_wid = %s AND m.channel_name = %s
              AND mh.mid IS NULL
            ORDER BY m.sent_at
            """,
            (uid, channel_wid, channel_name),
        )
        messages = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "home.html",
        channels=channels,
        messages=messages,
        channel_wid=channel_wid,
        channel_name=channel_name,
        current_channel=current_channel,
        now=datetime.now(timezone.utc),
    )


@app.route("/workspaces")
def workspaces():
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT w.wid, w.name, w.description
        FROM workspace w
        JOIN workspacemember wm ON w.wid = wm.wid
        WHERE wm.uid = %s AND wm.joined_at IS NOT NULL
        ORDER BY w.name
        """,
        (uid,),
    )
    data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("workspaces.html", workspaces=data)


@app.route("/create_workspace", methods=["GET", "POST"])
def create_workspace():
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    if request.method == "POST":
        name = request.form["name"]
        description = request.form.get("description") or ""
        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO workspace (name, description, created_at, created_by)
                VALUES (%s, %s, NOW(), %s)
                RETURNING wid
                """,
                (name, description, uid),
            )
            row = cur.fetchone()
            wid = row[0] if row else None
            if wid is None:
                raise RuntimeError("workspace insert failed")
            cur.execute(
                """
                INSERT INTO workspacemember (uid, wid, role, invited_at, joined_at)
                VALUES (%s, %s, 'admin', NOW(), NOW())
                """,
                (uid, wid),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
            conn.close()
        return redirect("/workspaces")
    return render_template("create_workspace.html")


@app.route("/workspace/<int:workspace_id>")
def workspace_detail(workspace_id):
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    if not user_is_workspace_member(cur, uid, workspace_id):
        cur.close()
        conn.close()
        return "You are not a member of this workspace.", 403
    cur.execute("SELECT * FROM workspace WHERE wid = %s", (workspace_id,))
    workspace = cur.fetchone()
    cur.execute(
        "SELECT * FROM channel WHERE wid = %s ORDER BY name", (workspace_id,)
    )
    chlist = cur.fetchall()
    members = None
    if is_workspace_admin(cur, uid, workspace_id):
        cur.execute(
            """
            SELECT u.uid, u.nickname, u.email
            FROM workspacemember wm
            JOIN "User" u ON wm.uid = u.uid
            WHERE wm.wid = %s AND wm.joined_at IS NOT NULL
            ORDER BY u.nickname
            """,
            (workspace_id,),
        )
        members = cur.fetchall()
    can_invite = is_workspace_admin(cur, uid, workspace_id)
    cur.close()
    conn.close()
    return render_template(
        "workspace_detail.html",
        workspace=workspace,
        channels=chlist,
        can_invite=can_invite,
        members=members,
    )


@app.route("/workspace/<int:workspace_id>/invite", methods=["GET", "POST"])
def invite_to_workspace(workspace_id):
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    if not is_workspace_admin(cur, uid, workspace_id):
        cur.close()
        conn.close()
        return "Only workspace administrators can send invitations.", 403
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        cur.execute('SELECT uid FROM "User" WHERE email = %s', (email,))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return render_template("invite_workspace.html", wid=workspace_id, error="User not found")
        target_uid = row[0]
        if target_uid == uid:
            cur.close()
            conn.close()
            return render_template("invite_workspace.html", wid=workspace_id, error="Cannot invite yourself")
        try:
            cur.execute(
                """
                INSERT INTO workspacemember (uid, wid, role, invited_at, joined_at)
                VALUES (%s, %s, 'member', NOW(), NULL)
                """,
                (target_uid, workspace_id),
            )
            conn.commit()
        except errors.UniqueViolation:
            conn.rollback()
            cur.close()
            conn.close()
            return render_template(
                "invite_workspace.html", wid=workspace_id, error="User already in workspace or invited"
            )
        cur.close()
        conn.close()
        return redirect(f"/workspace/{workspace_id}")
    cur.close()
    conn.close()
    return render_template("invite_workspace.html", wid=workspace_id, error=None)


@app.route("/invitations")
def invitations():
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT wm.wmid, w.name, w.wid, wm.invited_at
        FROM workspacemember wm
        JOIN workspace w ON w.wid = wm.wid
        WHERE wm.uid = %s AND wm.joined_at IS NULL AND wm.invited_at IS NOT NULL
        """,
        (uid,),
    )
    w_inv = cur.fetchall()
    cur.execute(
        """
        SELECT cm.cmid, c.name, c.wid, cm.invited_at, c.type
        FROM channelmember cm
        JOIN workspacemember wm ON cm.wmid = wm.wmid
        JOIN channel c ON c.wid = cm.channel_wid AND c.name = cm.channel_name
        WHERE wm.uid = %s
          AND cm.joined_at IS NULL
          AND cm.invited_at IS NOT NULL
        """,
        (uid,),
    )
    c_inv = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("invitations.html", workspace_invites=w_inv, channel_invites=c_inv)


@app.route("/invitations/workspace/<int:wmid>/accept", methods=["POST"])
def accept_workspace_invite(wmid):
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE workspacemember
        SET joined_at = NOW()
        WHERE wmid = %s AND uid = %s
          AND joined_at IS NULL AND invited_at IS NOT NULL
        """,
        (wmid, uid),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/invitations")


@app.route("/invitations/workspace/<int:wmid>/decline", methods=["POST"])
def decline_workspace_invite(wmid):
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM workspacemember WHERE wmid = %s AND uid = %s",
        (wmid, uid),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/invitations")


@app.route("/invitations/channel/<int:cmid>/accept", methods=["POST"])
def accept_channel_invite(cmid):
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE channelmember SET joined_at = NOW()
        WHERE cmid = %s
          AND joined_at IS NULL
          AND invited_at IS NOT NULL
          AND wmid IN (SELECT wmid FROM workspacemember WHERE uid = %s)
        """,
        (cmid, uid),
    )
    if cur.rowcount == 0:
        conn.rollback()
    else:
        conn.commit()
    cur.close()
    conn.close()
    return redirect("/invitations")


@app.route("/invitations/channel/<int:cmid>/decline", methods=["POST"])
def decline_channel_invite(cmid):
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        DELETE FROM channelmember
        WHERE cmid = %s
          AND wmid IN (SELECT wmid FROM workspacemember WHERE uid = %s)
        """,
        (cmid, uid),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect("/invitations")


@app.route("/channel/join")
def join_public_channel():
    """Join a public channel (query: channel_wid, channel_name)."""
    if "user_id" not in session:
        return redirect("/login")
    channel_wid = request.args.get("channel_wid", type=int)
    channel_name = request.args.get("channel_name", type=str)
    if not channel_wid or not channel_name:
        return "Missing parameters", 400
    channel_name = unquote(channel_name)
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT type FROM channel WHERE wid = %s AND name = %s",
        (channel_wid, channel_name),
    )
    r = cur.fetchone()
    if not r or r[0] != "public":
        cur.close()
        conn.close()
        return "This channel is not public or does not exist.", 403
    wmid = get_wmid_for_user_in_workspace(cur, uid, channel_wid)
    if wmid is None:
        cur.close()
        conn.close()
        return "You must be a member of the workspace first.", 403
    try:
        cur.execute(
            """
            INSERT INTO channelmember (wmid, channel_name, channel_wid, joined_at, invited_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            """,
            (wmid, channel_name, channel_wid),
        )
        conn.commit()
    except errors.UniqueViolation:
        conn.rollback()
        cur.execute(
            """
            UPDATE channelmember SET joined_at = NOW()
            WHERE wmid = %s AND channel_wid = %s AND channel_name = %s
              AND joined_at IS NULL
            """,
            (wmid, channel_wid, channel_name),
        )
        conn.commit()
    cur.close()
    conn.close()
    qn = quote(channel_name, safe="")
    return redirect(f"/home?channel_wid={channel_wid}&channel_name={qn}")


@app.route(
    "/channel/create/<int:workspace_id>",
    methods=["GET", "POST"],
)
def create_channel(workspace_id):
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    if not user_is_workspace_member(cur, uid, workspace_id):
        cur.close()
        conn.close()
        return "Not a workspace member", 403
    cur.execute(
        """
        SELECT u.uid, u.nickname, u.email
        FROM workspacemember wm
        JOIN "User" u ON wm.uid = u.uid
        WHERE wm.wid = %s AND wm.joined_at IS NOT NULL AND u.uid != %s
        ORDER BY u.nickname
        """,
        (workspace_id, uid),
    )
    other_members = cur.fetchall()
    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        ch_type = request.form.get("type", "public")
        if ch_type not in ("public", "private", "direct"):
            ch_type = "public"
        raw_peer = (request.form.get("peer_uid") or "").strip()
        peer_uid_raw = int(raw_peer) if raw_peer else None
        try:
            cur.execute(
                """
                INSERT INTO channel (name, wid, type, created_by)
                VALUES (%s, %s, %s, %s)
                """,
                (name, workspace_id, ch_type, uid),
            )
        except Exception as e:  # noqa: BLE001
            conn.rollback()
            cur.close()
            conn.close()
            return str(e), 400
        my_wmid = get_wmid_for_user_in_workspace(cur, uid, workspace_id)
        if ch_type in ("public", "private"):
            if my_wmid is not None:
                cur.execute(
                    """
                    INSERT INTO channelmember (wmid, channel_name, channel_wid, joined_at, invited_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    """,
                    (my_wmid, name, workspace_id),
                )
        elif ch_type == "direct":
            if not peer_uid_raw or peer_uid_raw == uid:
                conn.rollback()
                cur.close()
                conn.close()
                return "Direct channel requires another member", 400
            peer_wmid = get_wmid_for_user_in_workspace(cur, peer_uid_raw, workspace_id)
            if not my_wmid or not peer_wmid:
                conn.rollback()
                cur.close()
                conn.close()
                return "Both users must be in this workspace to create a direct channel", 400
            cur.execute(
                """
                INSERT INTO channelmember (wmid, channel_name, channel_wid, joined_at, invited_at)
                VALUES
                  (%s, %s, %s, NOW(), NOW()),
                  (%s, %s, %s, NOW(), NOW())
                """,
                (my_wmid, name, workspace_id, peer_wmid, name, workspace_id),
            )
        try:
            conn.commit()
        except Exception:
            conn.rollback()
            cur.close()
            conn.close()
            return "Failed to create channel (duplicate name in workspace?)", 400
        qn = quote(name, safe="")
        cur.close()
        conn.close()
        return redirect(
            f"/home?channel_wid={workspace_id}&channel_name={qn}"
        )
    cur.close()
    conn.close()
    return render_template(
        "create_channel.html",
        workspace_id=workspace_id,
        other_members=other_members,
    )


@app.route(
    "/channel/invite/<int:channel_wid>/<path:channel_name>",
    methods=["GET", "POST"],
)
def invite_to_channel(channel_wid, channel_name):
    if "user_id" not in session:
        return redirect("/login")
    channel_name = unquote(channel_name)
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT type FROM channel WHERE wid = %s AND name = %s",
        (channel_wid, channel_name),
    )
    row = cur.fetchone()
    if not row or row[0] != "private":
        cur.close()
        conn.close()
        return "Can only invite to private channels with this form.", 403
    if not can_manage_channel_invites(cur, uid, channel_wid, channel_name):
        cur.close()
        conn.close()
        return "Not allowed to invite to this channel.", 403
    if request.method == "POST":
        target_uid = request.form.get("target_uid", type=int)
        wmid = get_wmid_for_user_in_workspace(cur, target_uid, channel_wid) if target_uid else None
        if not wmid:
            cur.close()
            conn.close()
            return (
                "Invitee must be a full member of the workspace (joined) before channel invite",
                400,
            )
        try:
            cur.execute(
                """
                INSERT INTO channelmember (wmid, channel_name, channel_wid, invited_at, joined_at)
                VALUES (%s, %s, %s, NOW(), NULL)
                """,
                (wmid, channel_name, channel_wid),
            )
            conn.commit()
        except errors.UniqueViolation:
            conn.rollback()
            cur.close()
            conn.close()
            return "User already a member or invited to this channel", 400
        cur.close()
        conn.close()
        return redirect(
            f"/home?channel_wid={channel_wid}&channel_name={quote(channel_name, safe='')}"
        )
    cur.execute(
        """
        SELECT u.uid, u.nickname, u.email
        FROM workspacemember wm
        JOIN "User" u ON u.uid = wm.uid
        WHERE wm.wid = %s
          AND wm.joined_at IS NOT NULL
          AND wm.uid != %s
        ORDER BY u.nickname
        """,
        (channel_wid, uid),
    )
    candidates = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "invite_channel.html",
        channel_wid=channel_wid,
        channel_name=channel_name,
        candidates=candidates,
    )


@app.route("/channel/delete/<name>/<int:channel_wid>")
def delete_channel(name, channel_wid):
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    if not is_workspace_admin(cur, uid, channel_wid):
        cur.close()
        conn.close()
        return "Only workspace admins can delete channels", 403
    cur.execute(
        "DELETE FROM channel WHERE name = %s AND wid = %s", (name, channel_wid)
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/workspaces")


@app.route("/channel/<name>/<int:channel_wid>")
def channel_detail(name, channel_wid):
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT m.mid, m.content, u.nickname
        FROM message m
        JOIN channelmember cm ON m.cmid = cm.cmid
        JOIN workspacemember wm ON cm.wmid = wm.wmid
        JOIN "User" u ON wm.uid = u.uid
        WHERE m.channel_wid = %s AND m.channel_name = %s
        ORDER BY m.sent_at
        """,
        (channel_wid, name),
    )
    messages = cur.fetchall()
    cur.close()
    conn.close()
    return render_template(
        "channel_detail.html",
        messages=messages,
        channel_name=name,
        workspace_id=channel_wid,
    )


@app.route("/send_message", methods=["POST"])
def send_message():
    if "user_id" not in session:
        return redirect("/login")
    content = (request.form.get("content") or "").strip()
    channel_wid = request.form.get("channel_wid", type=int)
    channel_name = request.form.get("channel_name")
    if not content or not channel_wid or not channel_name:
        return redirect(request.referrer or "/home")
    channel_name = unquote(channel_name)
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cm.cmid, cm.channel_name, cm.channel_wid
        FROM channelmember cm
        JOIN workspacemember wm ON cm.wmid = wm.wmid
        WHERE wm.uid = %s
          AND cm.channel_wid = %s
          AND cm.channel_name = %s
          AND cm.joined_at IS NOT NULL
        """,
        (uid, channel_wid, channel_name),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return "You are not allowed to post in this channel", 403
    cmid, ch_name, ch_wid = row[0], row[1], row[2]
    try:
        cur.execute(
            """
            INSERT INTO message (content, channel_name, channel_wid, cmid, sent_at)
            VALUES (%s, %s, %s, %s, NOW())
            """,
            (content, ch_name, ch_wid, cmid),
        )
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
        cur.close()
        conn.close()
        return "Failed to post message", 500
    cur.close()
    conn.close()
    qn = quote(channel_name, safe="")
    return redirect(
        f"/home?channel_wid={channel_wid}&channel_name={qn}"
    )


@app.route("/message/recall/<int:mid>")
def recall_message(mid):
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    if not user_sent_message(cur, mid, uid):
        cur.close()
        conn.close()
        return "Not your message or message not found", 403
    try:
        cur.execute(
            """
            UPDATE message
            SET content = '[message was recalled]'
            WHERE mid = %s
            """,
            (mid,),
        )
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/home")


@app.route("/delete_message/<int:mid>")
def delete_message(mid):
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    if not user_sent_message(cur, mid, uid):
        cur.close()
        conn.close()
        return "Not your message", 403
    try:
        cur.execute(
            "INSERT INTO message_hidden (mid, uid) VALUES (%s, %s)",
            (mid, uid),
        )
        conn.commit()
    except errors.UniqueViolation:
        conn.rollback()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/home")


@app.route("/search", methods=["GET"])
def search_messages():
    if "user_id" not in session:
        return redirect("/login")
    q = (request.args.get("q") or "").strip()
    if not q:
        return render_template("search.html", q="", results=[])
    pattern = f"%{q}%"
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT ON (m.mid) m.content, m.sent_at, ch.name, ch.wid, send.nickname,
               m.channel_name, m.channel_wid
        FROM message m
        JOIN channel ch ON ch.name = m.channel_name AND ch.wid = m.channel_wid
        JOIN channelmember cm_send ON m.cmid = cm_send.cmid
        JOIN workspacemember wm_send ON cm_send.wmid = wm_send.wmid
        JOIN "User" send ON send.uid = wm_send.uid
        JOIN channelmember cm_v
          ON cm_v.channel_wid = m.channel_wid AND cm_v.channel_name = m.channel_name
        JOIN workspacemember wm_v ON cm_v.wmid = wm_v.wmid
        WHERE wm_v.uid = %s
          AND cm_v.joined_at IS NOT NULL
          AND m.content ILIKE %s
        ORDER BY m.mid, m.sent_at DESC
        """,
        (uid, pattern),
    )
    results = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("search.html", q=q, results=results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=True, host="0.0.0.0", port=port)
