from __future__ import annotations

import os
import re
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
        SELECT 1 FROM "WorkspaceMember"
        WHERE wid = %s AND uid = %s AND joined_at IS NOT NULL AND role = 'admin'
        """,
        (wid, uid),
    )
    return cursor.fetchone() is not None


def is_workspace_creator(cursor, uid: int, wid: int) -> bool:
    """True if uid is the user who created the workspace (Workspace.created_by)."""
    cursor.execute(
        'SELECT 1 FROM "Workspace" WHERE wid = %s AND created_by = %s',
        (wid, uid),
    )
    return cursor.fetchone() is not None


def get_wmid_for_user_in_workspace(cursor, uid: int, wid: int):
    cursor.execute(
        """
        SELECT wmid FROM "WorkspaceMember"
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
        SELECT 1 FROM "Message" m
        JOIN "ChannelMember" cm ON m.cmid = cm.cmid
        JOIN "WorkspaceMember" wm ON cm.wmid = wm.wmid
        WHERE m.mid = %s AND wm.uid = %s
        """,
        (mid, uid),
    )
    return cursor.fetchone() is not None


def _email_format_ok(value: str) -> bool:
    if not value or "@" not in value:
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", value.strip()))


def _dict_rows(keys: tuple[str, ...], rows: list) -> list[dict[str, object]]:
    """Map each DB row to a dict so templates do not depend on column order."""
    return [{k: v for k, v in zip(keys, row)} for row in rows]


def _owned_workspaces_with_members(cursor, uid: int) -> list[tuple[int, str, list[tuple[int, str]]]]:
    """Workspaces where uid is creator; each row is (wid, name, [(member_uid, label), ...])."""
    cursor.execute(
        """
        SELECT w.wid, w.name
        FROM "Workspace" w
        WHERE w.created_by = %s
        ORDER BY w.name
        """,
        (uid,),
    )
    owned = cursor.fetchall()
    result: list[tuple[int, str, list[tuple[int, str]]]] = []
    for wid, wname in owned:
        cursor.execute(
            """
            SELECT wm.uid, u.username, u.nickname
            FROM "WorkspaceMember" wm
            JOIN "User" u ON u.uid = wm.uid
            WHERE wm.wid = %s AND wm.joined_at IS NOT NULL AND wm.uid <> %s
            ORDER BY u.username
            """,
            (wid, uid),
        )
        members = []
        for m_uid, m_user, m_nick in cursor.fetchall():
            label = (m_nick or m_user).strip() or m_user
            members.append((m_uid, label))
        result.append((wid, wname, members))
    return result


def _reassign_channel_creators_to_workspace_owner(cursor, uid: int) -> None:
    """Resolve Channel.created_by FK before deleting user (channels in WS owned by others)."""
    cursor.execute(
        """
        UPDATE "Channel" c
        SET created_by = w.created_by
        FROM "Workspace" w
        WHERE c.wid = w.wid
          AND c.created_by = %s
          AND w.created_by <> %s
        """,
        (uid, uid),
    )


def can_manage_channel_invites(cursor, uid: int, channel_wid: int, channel_name: str) -> bool:
    """Channel creator or workspace admin may invite to a private channel."""
    if is_workspace_admin(cursor, uid, channel_wid):
        return True
    cursor.execute(
        """
        SELECT 1 FROM "Channel"
        WHERE name = %s AND wid = %s AND created_by = %s
        """,
        (channel_name, channel_wid, uid),
    )
    return cursor.fetchone() is not None


# ----- Routes -----


@app.route("/")
def index():
    return redirect("/home")


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


@app.route("/profile", methods=["GET"])
def profile():
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT email, username, nickname
        FROM "User"
        WHERE uid = %s
        """,
        (uid,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        session.clear()
        return redirect("/login")
    email, username, nickname = row
    owned = _owned_workspaces_with_members(cur, uid)
    cur.close()
    conn.close()
    return render_template(
        "profile.html",
        email=email or "",
        username=username or "",
        nickname=nickname or "",
        owned_workspaces=owned,
        account_error=None,
        account_success=None,
        password_error=None,
        password_success=None,
        delete_error=None,
    )


@app.route("/profile/account", methods=["POST"])
def profile_update_account():
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    email_raw = (request.form.get("email") or "").strip()
    username_raw = (request.form.get("username") or "").strip()
    nickname_raw = (request.form.get("nickname") or "").strip()

    if not email_raw:
        return _profile_render_with_errors(
            uid, account_error="Email is required."
        )
    if not _email_format_ok(email_raw):
        return _profile_render_with_errors(
            uid, account_error="Enter a valid email address."
        )
    if not username_raw:
        return _profile_render_with_errors(
            uid, account_error="Username is required."
        )

    nickname_db = nickname_raw if nickname_raw else None

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE "User"
            SET email = %s, username = %s, nickname = %s
            WHERE uid = %s
            """,
            (email_raw, username_raw, nickname_db, uid),
        )
        if cur.rowcount != 1:
            conn.rollback()
            cur.close()
            conn.close()
            return _profile_render_with_errors(uid, account_error="Update failed.")
        conn.commit()
    except errors.UniqueViolation:
        conn.rollback()
        cur.close()
        conn.close()
        return _profile_render_with_errors(
            uid,
            account_error="That email or username is already taken by another account.",
        )
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        cur.close()
        conn.close()
        return _profile_render_with_errors(uid, account_error=str(e))
    cur.close()
    conn.close()

    session["nickname"] = nickname_db or username_raw
    return _profile_render_with_errors(
        uid,
        account_success="Profile updated.",
        email=email_raw,
        username=username_raw,
        nickname=nickname_raw,
    )


@app.route("/profile/password", methods=["POST"])
def profile_update_password():
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    current_pw = request.form.get("current_password") or ""
    new_pw = request.form.get("new_password") or ""
    confirm_pw = request.form.get("confirm_password") or ""

    if not current_pw:
        return _profile_render_with_errors(
            uid, password_error="Current password is required."
        )
    if not new_pw:
        return _profile_render_with_errors(
            uid, password_error="New password is required."
        )
    if new_pw != confirm_pw:
        return _profile_render_with_errors(
            uid, password_error="New password and confirmation do not match."
        )

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM "User"
        WHERE uid = %s AND password = %s
        """,
        (uid, current_pw),
    )
    if cur.fetchone() is None:
        cur.close()
        conn.close()
        return _profile_render_with_errors(
            uid, password_error="Current password is incorrect."
        )
    try:
        cur.execute(
            'UPDATE "User" SET password = %s WHERE uid = %s',
            (new_pw, uid),
        )
        conn.commit()
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        cur.close()
        conn.close()
        return _profile_render_with_errors(uid, password_error=str(e))
    cur.close()
    conn.close()
    return _profile_render_with_errors(uid, password_success="Password changed.")


@app.route("/profile/delete", methods=["POST"])
def profile_delete_account():
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    password = request.form.get("password") or ""
    if not password:
        return _profile_render_with_errors(
            uid, delete_error="Enter your password to confirm account deletion."
        )

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM "User"
        WHERE uid = %s AND password = %s
        """,
        (uid, password),
    )
    if cur.fetchone() is None:
        cur.close()
        conn.close()
        return _profile_render_with_errors(
            uid, delete_error="Password is incorrect."
        )

    owned = _owned_workspaces_with_members(cur, uid)
    transfer_map: dict[int, int] = {}
    for wid, wname, members in owned:
        if not members:
            cur.close()
            conn.close()
            return _profile_render_with_errors(
                uid,
                delete_error=(
                    f'Workspace "{wname}" has no other active members. '
                    "Invite someone who can take ownership before deleting your account."
                ),
            )
        raw = request.form.get(f"transfer_{wid}") or ""
        if not raw.strip():
            cur.close()
            conn.close()
            return _profile_render_with_errors(
                uid,
                delete_error=(
                    f'Choose a member to receive ownership of workspace "{wname}".'
                ),
            )
        try:
            target_uid = int(raw)
        except ValueError:
            cur.close()
            conn.close()
            return _profile_render_with_errors(
                uid,
                delete_error=f"Invalid transferee selection for workspace \"{wname}\".",
            )
        allowed = {m[0] for m in members}
        if target_uid not in allowed:
            cur.close()
            conn.close()
            return _profile_render_with_errors(
                uid,
                delete_error=(
                    f'Selected user is not an eligible member of workspace "{wname}".'
                ),
            )
        transfer_map[wid] = target_uid

    try:
        for wid, new_owner in transfer_map.items():
            cur.execute(
                """
                UPDATE "Workspace"
                SET created_by = %s
                WHERE wid = %s AND created_by = %s
                """,
                (new_owner, wid, uid),
            )
            if cur.rowcount != 1:
                raise RuntimeError(f"transfer workspace {wid}")
            cur.execute(
                """
                UPDATE "Channel"
                SET created_by = %s
                WHERE wid = %s AND created_by = %s
                """,
                (new_owner, wid, uid),
            )
            cur.execute(
                """
                UPDATE "WorkspaceMember"
                SET role = 'admin'
                WHERE wid = %s AND uid = %s AND joined_at IS NOT NULL
                """,
                (wid, new_owner),
            )

        cur.execute(
            'SELECT 1 FROM "Workspace" WHERE created_by = %s LIMIT 1',
            (uid,),
        )
        if cur.fetchone() is not None:
            raise RuntimeError("still own workspaces")

        _reassign_channel_creators_to_workspace_owner(cur, uid)

        cur.execute(
            """
            SELECT 1 FROM "Channel" c
            JOIN "Workspace" w ON w.wid = c.wid
            WHERE c.created_by = %s AND w.created_by = %s
            LIMIT 1
            """,
            (uid, uid),
        )
        if cur.fetchone() is not None:
            raise RuntimeError("channel FK cleanup incomplete")

        cur.execute('DELETE FROM "User" WHERE uid = %s', (uid,))
        conn.commit()
    except Exception:
        conn.rollback()
        cur.close()
        conn.close()
        return _profile_render_with_errors(
            uid,
            delete_error="Could not delete account. Try again or contact support.",
        )
    cur.close()
    conn.close()
    session.clear()
    return redirect("/login")


def _profile_render_with_errors(
    uid: int,
    *,
    account_error: str | None = None,
    account_success: str | None = None,
    password_error: str | None = None,
    password_success: str | None = None,
    delete_error: str | None = None,
    email: str | None = None,
    username: str | None = None,
    nickname: str | None = None,
):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT email, username, nickname
        FROM "User"
        WHERE uid = %s
        """,
        (uid,),
    )
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        session.clear()
        return redirect("/login")
    db_email, db_username, db_nickname = row
    owned = _owned_workspaces_with_members(cur, uid)
    cur.close()
    conn.close()
    return render_template(
        "profile.html",
        email=email if email is not None else (db_email or ""),
        username=username if username is not None else (db_username or ""),
        nickname=nickname if nickname is not None else (db_nickname or ""),
        owned_workspaces=owned,
        account_error=account_error,
        account_success=account_success,
        password_error=password_error,
        password_success=password_success,
        delete_error=delete_error,
    )


def _load_sidebar_channels(cur, uid: int):
    """Channels the user may see in the sidebar: public in joined WSp, private/direct per rules."""
    cur.execute(
        """
        SELECT c.wid, c.name, c.type, w.name AS wname,
               EXISTS (
                   SELECT 1 FROM "ChannelMember" cm2
                   JOIN "WorkspaceMember" wm2 ON cm2.wmid = wm2.wmid
                   WHERE cm2.channel_wid = c.wid
                     AND cm2.channel_name = c.name
                     AND wm2.uid = %s
                     AND wm2.wid = c.wid
                     AND cm2.joined_at IS NOT NULL
               ) AS is_joined
        FROM "Channel" c
        JOIN "Workspace" w ON c.wid = w.wid
        JOIN "WorkspaceMember" wm ON wm.wid = w.wid
            AND wm.uid = %s AND wm.joined_at IS NOT NULL
        WHERE
            c.type = 'public'
            OR (c.type = 'private' AND EXISTS (
                SELECT 1 FROM "ChannelMember" cm3
                JOIN "WorkspaceMember" wmx ON cm3.wmid = wmx.wmid
                WHERE cm3.channel_wid = c.wid
                  AND cm3.channel_name = c.name
                  AND wmx.uid = %s
            ))
            OR (c.type = 'direct' AND EXISTS (
                SELECT 1 FROM "ChannelMember" cm3
                JOIN "WorkspaceMember" wmx ON cm3.wmid = wmx.wmid
                WHERE cm3.channel_wid = c.wid
                  AND cm3.channel_name = c.name
                  AND wmx.uid = %s
                  AND cm3.joined_at IS NOT NULL
            ))
        ORDER BY w.name, c.name
        """,
        (uid, uid, uid, uid),
    )
    return _dict_rows(
        ("wid", "name", "channel_type", "workspace_name", "is_joined"),
        cur.fetchall(),
    )


@app.route("/home")
def home():
    """Dashboard: greeting, workspace list, pending workspace invites."""
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT w.wid, w.name, w.description
        FROM "Workspace" w
        JOIN "WorkspaceMember" wm ON w.wid = wm.wid
        WHERE wm.uid = %s AND wm.joined_at IS NOT NULL
        ORDER BY w.name
        """,
        (uid,),
    )
    workspaces_list = _dict_rows(("wid", "name", "description"), cur.fetchall())
    cur.execute(
        """
        SELECT wm.wmid, w.name, w.wid, wm.invited_at
        FROM "WorkspaceMember" wm
        JOIN "Workspace" w ON w.wid = wm.wid
        WHERE wm.uid = %s AND wm.joined_at IS NULL AND wm.invited_at IS NOT NULL
        ORDER BY wm.invited_at DESC
        """,
        (uid,),
    )
    workspace_invites = _dict_rows(
        ("wmid", "workspace_name", "wid", "invited_at"), cur.fetchall()
    )
    cur.close()
    conn.close()
    return render_template(
        "home.html",
        workspaces=workspaces_list,
        workspace_invites=workspace_invites,
    )


@app.route("/chat")
def chat():
    """Main messaging UI with channel sidebar (opened from a channel link)."""
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
            FROM "Channel" ch
            JOIN "WorkspaceMember" wm ON ch.wid = wm.wid
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
            FROM "Channel" ch
            JOIN "ChannelMember" cm ON ch.name = cm.channel_name AND ch.wid = cm.channel_wid
            JOIN "WorkspaceMember" wm ON cm.wmid = wm.wmid
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
            FROM "Message" m
            JOIN "ChannelMember" cm ON m.cmid = cm.cmid
            JOIN "WorkspaceMember" wm ON cm.wmid = wm.wmid
            JOIN "User" u ON wm.uid = u.uid
            WHERE m.channel_wid = %s AND m.channel_name = %s
              AND NOT m.is_deleted
              AND NOT EXISTS (
                SELECT 1 FROM "MessageHidden" mh
                WHERE mh.mid = m.mid AND mh.uid = %s
              )
            ORDER BY m.sent_at
            """,
            (channel_wid, channel_name, uid),
        )
        messages = _dict_rows(
            ("mid", "content", "nickname", "sent_at", "can_recall"), cur.fetchall()
        )

    cur.close()
    conn.close()

    return render_template(
        "chat.html",
        channels=channels,
        messages=messages,
        channel_wid=channel_wid,
        channel_name=channel_name,
        current_channel=current_channel,
        now=datetime.now(timezone.utc),
    )


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
                INSERT INTO "Workspace" (name, description, created_at, created_by)
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
                INSERT INTO "WorkspaceMember" (uid, wid, role, invited_at, joined_at)
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
        return redirect("/home")
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
    cur.execute(
        """
        SELECT wid, name, description, created_by
        FROM "Workspace"
        WHERE wid = %s
        """,
        (workspace_id,),
    )
    row = cur.fetchone()
    if row is None:
        cur.close()
        conn.close()
        return "Workspace not found.", 404
    workspace = {
        "wid": row[0],
        "name": row[1],
        "description": row[2],
        "created_by": row[3],
    }
    cur.execute(
        """
        SELECT c.name, c.wid, c.type,
               (cm.cmid IS NOT NULL) AS is_channel_member
        FROM "Channel" c
        JOIN "WorkspaceMember" wm
          ON wm.wid = c.wid AND wm.uid = %s AND wm.joined_at IS NOT NULL
        LEFT JOIN "ChannelMember" cm
          ON cm.wmid = wm.wmid
          AND cm.channel_name = c.name
          AND cm.channel_wid = c.wid
          AND cm.joined_at IS NOT NULL
        WHERE c.wid = %s
        ORDER BY c.name
        """,
        (uid, workspace_id),
    )
    chlist = _dict_rows(("name", "wid", "type", "is_channel_member"), cur.fetchall())
    is_workspace_admin_user = is_workspace_admin(cur, uid, workspace_id)
    members = None
    if is_workspace_admin_user:
        cur.execute(
            """
            SELECT u.uid, u.nickname, u.email, wm.role,
                   (w.created_by = u.uid) AS is_workspace_creator
            FROM "WorkspaceMember" wm
            JOIN "User" u ON wm.uid = u.uid
            JOIN "Workspace" w ON w.wid = wm.wid
            WHERE wm.wid = %s AND wm.joined_at IS NOT NULL
            ORDER BY u.nickname
            """,
            (workspace_id,),
        )
        members = _dict_rows(
            ("uid", "nickname", "email", "role", "is_workspace_creator"),
            cur.fetchall(),
        )
    viewer_is_workspace_creator = is_workspace_creator(cur, uid, workspace_id)
    for ch in chlist:
        ch["can_invite_to_channel"] = can_manage_channel_invites(
            cur, uid, workspace_id, str(ch["name"])
        )
    cur.close()
    conn.close()
    return render_template(
        "workspace_detail.html",
        workspace=workspace,
        channels=chlist,
        can_invite_to_workspace=is_workspace_admin_user,
        members=members,
        viewer_is_workspace_creator=viewer_is_workspace_creator,
    )


@app.route(
    "/workspace/<int:workspace_id>/members/<int:target_uid>/role",
    methods=["POST"],
)
def workspace_set_member_role(workspace_id, target_uid):
    """Only the workspace creator may grant or revoke admin role (confirmed via created_by)."""
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    new_role = (request.form.get("role") or "").strip()
    if new_role not in ("admin", "member"):
        return "Invalid role.", 400
    conn = get_db()
    cur = conn.cursor()
    if not is_workspace_creator(cur, uid, workspace_id):
        cur.close()
        conn.close()
        return (
            "Only the workspace creator can change who is an administrator.",
            403,
        )
    cur.execute(
        'SELECT created_by FROM "Workspace" WHERE wid = %s',
        (workspace_id,),
    )
    ws_row = cur.fetchone()
    if not ws_row:
        cur.close()
        conn.close()
        return "Workspace not found.", 404
    creator_uid = ws_row[0]
    if target_uid == creator_uid:
        cur.close()
        conn.close()
        return (
            "The workspace creator's administrator status cannot be changed here.",
            403,
        )
    cur.execute(
        """
        SELECT 1 FROM "WorkspaceMember"
        WHERE wid = %s AND uid = %s AND joined_at IS NOT NULL
        """,
        (workspace_id, target_uid),
    )
    if not cur.fetchone():
        cur.close()
        conn.close()
        return "That user is not an active member of this workspace.", 400
    cur.execute(
        """
        UPDATE "WorkspaceMember"
        SET role = %s
        WHERE wid = %s AND uid = %s
        """,
        (new_role, workspace_id, target_uid),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("workspace_detail", workspace_id=workspace_id))


@app.route(
    "/workspace/<int:workspace_id>/members/<int:target_uid>/remove",
    methods=["POST"],
)
def workspace_remove_member(workspace_id, target_uid):
    """Workspace admins may remove members; the workspace creator cannot be removed."""
    if "user_id" not in session:
        return redirect("/login")
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    if not is_workspace_admin(cur, uid, workspace_id):
        cur.close()
        conn.close()
        return "Only workspace administrators can remove members.", 403
    if target_uid == uid:
        cur.close()
        conn.close()
        return "You cannot remove yourself from the workspace here.", 403
    cur.execute(
        'SELECT created_by FROM "Workspace" WHERE wid = %s',
        (workspace_id,),
    )
    ws_row = cur.fetchone()
    if not ws_row:
        cur.close()
        conn.close()
        return "Workspace not found.", 404
    if target_uid == ws_row[0]:
        cur.close()
        conn.close()
        return "The workspace creator cannot be removed from the workspace.", 403
    cur.execute(
        """
        DELETE FROM "WorkspaceMember"
        WHERE wid = %s AND uid = %s AND joined_at IS NOT NULL
        """,
        (workspace_id, target_uid),
    )
    if cur.rowcount == 0:
        conn.rollback()
        cur.close()
        conn.close()
        return "User is not a joined member of this workspace.", 400
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("workspace_detail", workspace_id=workspace_id))


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
                INSERT INTO "WorkspaceMember" (uid, wid, role, invited_at, joined_at)
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
        FROM "WorkspaceMember" wm
        JOIN "Workspace" w ON w.wid = wm.wid
        WHERE wm.uid = %s AND wm.joined_at IS NULL AND wm.invited_at IS NOT NULL
        """,
        (uid,),
    )
    w_inv = _dict_rows(("wmid", "workspace_name", "wid", "invited_at"), cur.fetchall())
    cur.execute(
        """
        SELECT cm.cmid, c.name, c.wid, cm.invited_at, c.type
        FROM "ChannelMember" cm
        JOIN "WorkspaceMember" wm ON cm.wmid = wm.wmid
        JOIN "Channel" c ON c.wid = cm.channel_wid AND c.name = cm.channel_name
        WHERE wm.uid = %s
          AND cm.joined_at IS NULL
          AND cm.invited_at IS NOT NULL
        """,
        (uid,),
    )
    c_inv = _dict_rows(
        ("cmid", "channel_name", "wid", "invited_at", "channel_type"), cur.fetchall()
    )
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
        UPDATE "WorkspaceMember"
        SET joined_at = NOW()
        WHERE wmid = %s AND uid = %s
          AND joined_at IS NULL AND invited_at IS NOT NULL
        RETURNING wid
        """,
        (wmid, uid),
    )
    accepted_row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    if accepted_row:
        wid = accepted_row[0]
        return redirect(url_for("workspace_detail", workspace_id=wid))
    return redirect("/invitations")


@app.route("/invitations/workspace/<int:wmid>/decline", methods=["POST"])
def decline_workspace_invite(wmid):
    uid = _require_user_id()
    if uid is None:
        return redirect("/login")
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        'DELETE FROM "WorkspaceMember" WHERE wmid = %s AND uid = %s',
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
        UPDATE "ChannelMember" SET joined_at = NOW()
        WHERE cmid = %s
          AND joined_at IS NULL
          AND invited_at IS NOT NULL
          AND wmid IN (SELECT wmid FROM "WorkspaceMember" WHERE uid = %s)
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
        DELETE FROM "ChannelMember"
        WHERE cmid = %s
          AND wmid IN (SELECT wmid FROM "WorkspaceMember" WHERE uid = %s)
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
        'SELECT type FROM "Channel" WHERE wid = %s AND name = %s',
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
            INSERT INTO "ChannelMember" (wmid, channel_name, channel_wid, joined_at, invited_at)
            VALUES (%s, %s, %s, NOW(), NOW())
            """,
            (wmid, channel_name, channel_wid),
        )
        conn.commit()
    except errors.UniqueViolation:
        conn.rollback()
        cur.execute(
            """
            UPDATE "ChannelMember" SET joined_at = NOW()
            WHERE wmid = %s AND channel_wid = %s AND channel_name = %s
              AND joined_at IS NULL
            """,
            (wmid, channel_wid, channel_name),
        )
        conn.commit()
    cur.close()
    conn.close()
    qn = quote(channel_name, safe="")
    return redirect(f"/chat?channel_wid={channel_wid}&channel_name={qn}")


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
        FROM "WorkspaceMember" wm
        JOIN "User" u ON wm.uid = u.uid
        WHERE wm.wid = %s AND wm.joined_at IS NOT NULL AND u.uid != %s
        ORDER BY u.nickname
        """,
        (workspace_id, uid),
    )
    other_members = _dict_rows(("uid", "nickname", "email"), cur.fetchall())
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
                INSERT INTO "Channel" (name, wid, type, created_by)
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
                    INSERT INTO "ChannelMember" (wmid, channel_name, channel_wid, joined_at, invited_at)
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
                INSERT INTO "ChannelMember" (wmid, channel_name, channel_wid, joined_at, invited_at)
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
            f"/chat?channel_wid={workspace_id}&channel_name={qn}"
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
        'SELECT type FROM "Channel" WHERE wid = %s AND name = %s',
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
                INSERT INTO "ChannelMember" (wmid, channel_name, channel_wid, invited_at, joined_at)
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
            f"/chat?channel_wid={channel_wid}&channel_name={quote(channel_name, safe='')}"
        )
    cur.execute(
        """
        SELECT u.uid, u.nickname, u.email
        FROM "WorkspaceMember" wm
        JOIN "User" u ON u.uid = wm.uid
        WHERE wm.wid = %s
          AND wm.joined_at IS NOT NULL
          AND wm.uid != %s
        ORDER BY u.nickname
        """,
        (channel_wid, uid),
    )
    candidates = _dict_rows(("uid", "nickname", "email"), cur.fetchall())
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
        'DELETE FROM "Channel" WHERE name = %s AND wid = %s', (name, channel_wid)
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/workspaces")


@app.route("/send_message", methods=["POST"])
def send_message():
    if "user_id" not in session:
        return redirect("/login")
    content = (request.form.get("content") or "").strip()
    channel_wid = request.form.get("channel_wid", type=int)
    channel_name = request.form.get("channel_name")
    if not content or not channel_wid or not channel_name:
        return redirect(request.referrer or "/chat")
    channel_name = unquote(channel_name)
    uid = int(session["user_id"])
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT cm.cmid, cm.channel_name, cm.channel_wid
        FROM "ChannelMember" cm
        JOIN "WorkspaceMember" wm ON cm.wmid = wm.wmid
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
            INSERT INTO "Message" (content, channel_name, channel_wid, cmid, sent_at)
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
        f"/chat?channel_wid={channel_wid}&channel_name={qn}"
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
            UPDATE "Message"
            SET content = '[message was recalled]', is_recalled = TRUE
            WHERE mid = %s
            """,
            (mid,),
        )
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/chat")


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
            """
            INSERT INTO "MessageHidden" (mid, uid)
            VALUES (%s, %s)
            ON CONFLICT (mid, uid) DO NOTHING
            """,
            (mid, uid),
        )
        conn.commit()
    except Exception:  # noqa: BLE001
        conn.rollback()
    cur.close()
    conn.close()
    return redirect(request.referrer or "/chat")


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
        FROM "Message" m
        JOIN "Channel" ch ON ch.name = m.channel_name AND ch.wid = m.channel_wid
        JOIN "ChannelMember" cm_send ON m.cmid = cm_send.cmid
        JOIN "WorkspaceMember" wm_send ON cm_send.wmid = wm_send.wmid
        JOIN "User" send ON send.uid = wm_send.uid
        JOIN "ChannelMember" cm_v
          ON cm_v.channel_wid = m.channel_wid AND cm_v.channel_name = m.channel_name
        JOIN "WorkspaceMember" wm_v ON cm_v.wmid = wm_v.wmid
        WHERE wm_v.uid = %s
          AND cm_v.joined_at IS NOT NULL
          AND NOT m.is_deleted
          AND NOT EXISTS (
            SELECT 1 FROM "MessageHidden" mh
            WHERE mh.mid = m.mid AND mh.uid = %s
          )
          AND m.content ILIKE %s
        ORDER BY m.mid, m.sent_at DESC
        """,
        (uid, uid, pattern),
    )
    results = _dict_rows(
        ("content", "sent_at", "channel_name", "workspace_id", "sender_nickname"),
        cur.fetchall(),
    )
    cur.close()
    conn.close()
    return render_template("search.html", q=q, results=results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(debug=True, host="0.0.0.0", port=port)
