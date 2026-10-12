
import os
import sqlite3
from pathlib import Path
from datetime import datetime, timezone


# Railway Volume можно подключить к /data.
# Для локального запуска используется папка ./data.
DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "devpocket.db"

MAX_PROJECTS_PER_USER = 30
MAX_PROJECT_NAME_LENGTH = 80
MAX_CONTENT_LENGTH = 100_000


def get_connection():
    connection = sqlite3.connect(
        str(DB_PATH),
        timeout=10,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def now_utc():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                language TEXT NOT NULL DEFAULT 'python',
                content TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_owner
            ON projects(owner_id, updated_at DESC)
        """)

    print("DevPocket database initialized")


def project_to_dict(row):
    if row is None:
        return None

    return {
        "id": row["id"],
        "name": row["name"],
        "language": row["language"],
        "content": row["content"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def list_projects(owner_id):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, language, content,
                   created_at, updated_at
            FROM projects
            WHERE owner_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (owner_id,),
        ).fetchall()

    return [project_to_dict(row) for row in rows]


def get_project(owner_id, project_id):
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, language, content,
                   created_at, updated_at
            FROM projects
            WHERE owner_id = ? AND id = ?
            """,
            (owner_id, project_id),
        ).fetchone()

    return project_to_dict(row)


def create_project(owner_id, name, language="python", content=""):
    name = validate_name(name)
    language = validate_language(language)
    content = validate_content(content)

    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM projects WHERE owner_id = ?",
            (owner_id,),
        ).fetchone()[0]

        if count >= MAX_PROJECTS_PER_USER:
            raise ValueError(
                f"Maximum {MAX_PROJECTS_PER_USER} projects per user"
            )

        timestamp = now_utc()

        cursor = connection.execute(
            """
            INSERT INTO projects (
                owner_id, name, language, content,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                owner_id,
                name,
                language,
                content,
                timestamp,
                timestamp,
            ),
        )

        project_id = cursor.lastrowid

    return get_project(owner_id, project_id)


def update_project(
    owner_id,
    project_id,
    name,
    language,
    content,
):
    name = validate_name(name)
    language = validate_language(language)
    content = validate_content(content)

    with get_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE projects
            SET name = ?,
                language = ?,
                content = ?,
                updated_at = ?
            WHERE owner_id = ? AND id = ?
            """,
            (
                name,
                language,
                content,
                now_utc(),
                owner_id,
                project_id,
            ),
        )

        if cursor.rowcount == 0:
            return None

    return get_project(owner_id, project_id)


def delete_project(owner_id, project_id):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            DELETE FROM projects
            WHERE owner_id = ? AND id = ?
            """,
            (owner_id, project_id),
        )

        return cursor.rowcount > 0


def validate_name(name):
    if not isinstance(name, str):
        raise ValueError("Project name must be text")

    name = name.strip()

    if not name:
        raise ValueError("Project name cannot be empty")

    if len(name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError(
            f"Project name must be at most "
            f"{MAX_PROJECT_NAME_LENGTH} characters"
        )

    return name


def validate_language(language):
    allowed_languages = {
        "python",
        "javascript",
        "typescript",
        "html",
        "css",
        "json",
        "text",
    }

    if not isinstance(language, str):
        raise ValueError("Language must be text")

    language = language.strip().lower()

    if language not in allowed_languages:
        raise ValueError("Unsupported project language")

    return language


def validate_content(content):
    if not isinstance(content, str):
        raise ValueError("Project content must be text")

    if len(content) > MAX_CONTENT_LENGTH:
        raise ValueError(
            f"Content must be at most {MAX_CONTENT_LENGTH} characters"
        )

    return content
