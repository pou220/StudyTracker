from datetime import datetime, timezone
from flask_login import UserMixin
from extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False)
    email: str = db.Column(db.String(120), unique=True, nullable=False)
    password_hash: str = db.Column(db.String(256), nullable=False)
    avatar_filename: str = db.Column(db.String(255), nullable=True)
    created_at: datetime = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    target_university = db.Column(db.String(100), nullable=True)
    subjects = db.relationship(
        "Subject",
        backref="user",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username='{self.username}'>"

    def get_total_tasks(self) -> int:
        return (
            db.session.query(Task)
            .join(Subject)
            .filter(Subject.user_id == self.id)
            .count()
        )

    def get_completed_tasks(self) -> int:
        return (
            db.session.query(Task)
            .join(Subject)
            .filter(Subject.user_id == self.id, Task.is_done == True)
            .count()
        )


class Subject(db.Model):
    __tablename__ = "subjects"

    id: int = db.Column(db.Integer, primary_key=True)
    name: str = db.Column(db.String(100), nullable=False)
    target_score: int = db.Column(db.Integer, nullable=True)
    color: str = db.Column(db.String(7), nullable=False, default="#0d6efd")
    created_at: datetime = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    user_id: int = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    tasks = db.relationship(
        "Task",
        backref="subject",
        cascade="all, delete-orphan",
        order_by="Task.created_at.desc()"
    )

    def __repr__(self) -> str:
        return f"<Subject id={self.id} name='{self.name}' user_id={self.user_id}>"

    def get_done_tasks_count(self) -> int:
        return sum(1 for task in self.tasks if task.is_done)

    def get_progress_percent(self) -> int:
        total = len(self.tasks)
        return int(self.get_done_tasks_count() / total * 100) if total else 0


class Task(db.Model):
    PRIORITY_LOW = "low"
    PRIORITY_MEDIUM = "medium"
    PRIORITY_HIGH = "high"
    PRIORITY_CHOICES = [PRIORITY_LOW, PRIORITY_MEDIUM, PRIORITY_HIGH]

    __tablename__ = "tasks"

    id: int = db.Column(db.Integer, primary_key=True)
    title: str = db.Column(db.String(200), nullable=False)
    description: str = db.Column(db.Text, nullable=True)
    is_done: bool = db.Column(db.Boolean, nullable=False, default=False)
    priority: str = db.Column(db.String(10), nullable=False, default=PRIORITY_MEDIUM)
    due_date: datetime = db.Column(db.DateTime, nullable=True)
    created_at: datetime = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    subject_id: int = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    files = db.relationship(
        "TaskFile",
        backref="task",
        cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Task id={self.id} title='{self.title[:30]}' "
            f"is_done={self.is_done} priority='{self.priority}'>"
        )

    def toggle_done(self) -> bool:
        self.is_done = not self.is_done
        return self.is_done

    def is_overdue(self) -> bool:
        if self.due_date is None or self.is_done:
            return False
        return datetime.now(timezone.utc) > self.due_date.replace(tzinfo=timezone.utc)

    def get_priority_badge_class(self) -> str:
        priority_map = {
            self.PRIORITY_HIGH: "bg-danger",
            self.PRIORITY_MEDIUM: "bg-warning text-dark",
            self.PRIORITY_LOW: "bg-secondary",
        }
        return priority_map.get(self.priority, "bg-secondary")


class TaskFile(db.Model):
    __tablename__ = "task_files"

    id: int = db.Column(db.Integer, primary_key=True)
    original_filename: str = db.Column(db.String(255), nullable=False)
    stored_filename: str = db.Column(db.String(255), nullable=False, unique=True)
    file_size: int = db.Column(db.Integer, nullable=True)
    uploaded_at: datetime = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    task_id: int = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)

    def __repr__(self) -> str:
        return f"<TaskFile id={self.id} original='{self.original_filename}' task_id={self.task_id}>"

    def get_file_size_kb(self) -> str:
        if self.file_size is None:
            return "—"
        return f"{self.file_size / 1024:.1f} КБ"


@login_manager.user_loader
def load_user(user_id):
    if not user_id or user_id == "None":
        return None
    try:
        return db.session.get(User, int(user_id))
    except (ValueError, TypeError):
        return None