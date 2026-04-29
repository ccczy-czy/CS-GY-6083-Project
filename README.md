# CS-GY-6083 Project

This is a draft. Still completing... The feature list is a draft to help write final report later.

## Features

### Authentication and users

- **Register** with email, username, nickname, and password
- **Log in** and **log out** (session-based, uses cookie underlying)

### Profile and account

- **View and edit** email, username, and nickname (with validation)
- **Change password** (current password required)
- **Delete account** with password confirmation; if you **own workspaces**, you must **transfer ownership** to another member before deletion

### Workspaces

- **Create workspace** with name and description; creator becomes an **admin** and is auto-joined
- **Home dashboard** lists joined workspaces and **pending workspace invitations**
- **Workspace detail** shows channels and membership; **admins** see the member list
- **Invite users to workspace** by email (admins only); invitees get a pending join until they accept
- **Workspace admin**: remove members (not the creator), or **delete channels**
- **Workspace creator only**: **promote/demote** other members between `admin` and `member` roles
- **Pending invitations** page: accept or decline **workspace** and **private channel** invites

### Channels

- **Create channels** inside a workspace: **public**, **private**, or **direct** (1:1 with another workspace member)
- **Join public channels** (must already be a workspace member)
- **Private channels**: workspace admins or channel creator can **invite** workspace members; invitees must **accept** on the invitations page before chatting
- **Delete channel** (workspace admins only)

### Messaging

- **Chat** view with a **channel sidebar** (all channels you can see in joined workspaces)
- **Send messages** in channels you have joined
- **Recall** your own message within a short window (replaced with “[message was recalled]”)
- **Hide message for yourself** (soft “delete” via `MessageHidden` without removing it for others)
- **Search** messages you can access, with links back to the channel

### Deployment configuration

Coming back later

---

## Run locally

### Docker Compose (Need to install Docker and Docker Compose first)

From the project root:

1. **Start the stack** (builds the web image, starts PostgreSQL and the app):

   ```bash
   docker compose up --build
   ```

2. **Open the app** in a browser: [http://localhost:5000](http://localhost:5000)

3. **Stop** with `Ctrl+C` or `docker compose down`. To **reset the database** completely, remove the named volume (this deletes all data):

   ```bash
   docker compose down -v
   ```

## Project layout (high level)

Coming back later.
