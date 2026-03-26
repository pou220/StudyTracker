import os
import logging
from datetime import datetime, timezone

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    abort,
    send_from_directory,
    jsonify,
    current_app,
)
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db, bcrypt
from models import User, Subject, Task, TaskFile
from forms import (
    RegistrationForm,
    LoginForm,
    SubjectForm,
    TaskForm,
    AvatarUploadForm,
    DeleteForm,
    UpdateGoalForm,
)
from utils import (
    save_uploaded_file,
    delete_file_from_disk,
    fetch_random_dog_image,
    calculate_dashboard_stats,
    is_allowed_file,
)

main = Blueprint("main", __name__)
logger = logging.getLogger("study_tracker.routes")


def _get_subject_or_404(subject_id: int) -> Subject:
    subject = db.session.get(Subject, subject_id)
    if subject is None:
        logger.warning("Предмет id=%d не найден (user_id=%d)", subject_id, current_user.id)
        abort(404)
    if subject.user_id != current_user.id:
        logger.warning(
            "Попытка доступа к чужому предмету: subject_id=%d, owner_id=%d, requester_id=%d",
            subject_id, subject.user_id, current_user.id,
        )
        abort(403)
    return subject


def _get_task_or_404(task_id: int) -> Task:
    task = db.session.get(Task, task_id)
    if task is None:
        logger.warning("Задача id=%d не найдена (user_id=%d)", task_id, current_user.id)
        abort(404)
    if task.subject.user_id != current_user.id:
        logger.warning("Попытка доступа к чужой задаче: task_id=%d, requester_id=%d", task_id, current_user.id)
        abort(403)
    return task


def _commit_or_rollback(operation_name: str) -> bool:
    try:
        db.session.commit()
        logger.info("БД: успешный коммит — %s", operation_name)
        return True
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error("БД: ошибка при %s, транзакция откатана. Причина: %s", operation_name, exc)
        return False


@main.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegistrationForm()

    if form.validate_on_submit():
        password_hash = bcrypt.generate_password_hash(form.password.data).decode("utf-8")

        university = form.target_university.data
        if university == "Другой" and form.other_university.data:
            university = form.other_university.data.strip()

        new_user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
            password_hash=password_hash,
            target_university=university,
        )
        db.session.add(new_user)

        if _commit_or_rollback("регистрация пользователя"):
            login_user(new_user, remember=False)
            flash(f"🎉 Добро пожаловать, {new_user.username}!", "success")
            return redirect(url_for("main.dashboard"))
        else:
            flash("Произошла ошибка при создании аккаунта. Пожалуйста, попробуйте ещё раз.", "danger")

    return render_template("register.html", title="Регистрация", form=form)


@main.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()

        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            login_user(user, remember=form.remember_me.data)
            logger.info(
                "Вход: id=%d, username='%s', remember=%s",
                user.id, user.username, form.remember_me.data,
            )
            flash(f"С возвращением, {user.username}! 👋", "success")

            next_page = request.args.get("next")
            if next_page and next_page.startswith("/"):
                return redirect(next_page)
            return redirect(url_for("main.dashboard"))
        else:
            logger.warning("Неудачный вход для email='%s'", form.email.data)
            flash("Неверный email или пароль. Проверьте введённые данные.", "danger")

    return render_template("login.html", title="Вход", form=form)


@main.route("/logout")
@login_required
def logout():
    username = current_user.username
    logout_user()
    logger.info("Выход: '%s'", username)
    flash(f"До свидания, {username}! Вы вышли из системы.", "info")
    return redirect(url_for("main.login"))


@main.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("main.login"))


@main.route("/dashboard")
@login_required
def dashboard():
    subjects = (
        Subject.query
        .filter_by(user_id=current_user.id)
        .order_by(Subject.created_at.desc())
        .all()
    )
    stats = calculate_dashboard_stats(current_user)
    upcoming_tasks = (
        Task.query
        .join(Subject)
        .filter(
            Subject.user_id == current_user.id,
            Task.is_done == False,  # noqa: E712
            Task.due_date.isnot(None),
        )
        .order_by(Task.due_date.asc())
        .limit(5)
        .all()
    )
    high_priority_tasks = (
        Task.query
        .join(Subject)
        .filter(
            Subject.user_id == current_user.id,
            Task.is_done == False,  # noqa: E712
            Task.priority == Task.PRIORITY_HIGH,
        )
        .order_by(Task.created_at.desc())
        .limit(5)
        .all()
    )
    goal_form = UpdateGoalForm()
    if current_user.target_university in ["МИФИ", "СГТУ", "СГУ", "РАНХиГС"]:
        goal_form.target_university.data = current_user.target_university
    elif current_user.target_university:
        goal_form.target_university.data = "Другой"
        goal_form.other_university.data = current_user.target_university

    return render_template(
        "dashboard.html",
        title="Мой дашборд",
        subjects=subjects,
        stats=stats,
        upcoming_tasks=upcoming_tasks,
        high_priority_tasks=high_priority_tasks,
        delete_form=DeleteForm(),
        goal_form=goal_form,
    )


@main.route("/update_goal", methods=["POST"])
@login_required
def update_goal():
    form = UpdateGoalForm()
    if form.validate_on_submit():
        university = form.target_university.data
        if university == "Другой" and form.other_university.data:
            university = form.other_university.data.strip()

        current_user.target_university = university

        if _commit_or_rollback("обновление цели"):
            flash("🎯 Цель успешно обновлена!", "success")
        else:
            flash("Ошибка при обновлении цели.", "danger")
    else:
        flash("Ошибка в форме. Проверьте данные.", "danger")

    return redirect(url_for("main.dashboard"))


@main.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    avatar_form = AvatarUploadForm()
    stats = calculate_dashboard_stats(current_user)

    if avatar_form.validate_on_submit():
        file_storage = avatar_form.avatar.data
        if file_storage and file_storage.filename and file_storage.filename.strip():
            try:
                if current_user.avatar_filename:
                    delete_file_from_disk(current_user.avatar_filename, subfolder="avatars")

                _original, stored_filename, _size = save_uploaded_file(file_storage, subfolder="avatars")
                current_user.avatar_filename = stored_filename

                if _commit_or_rollback("обновление аватара"):
                    flash("Аватар успешно обновлён! ✨", "success")
                else:
                    delete_file_from_disk(stored_filename, subfolder="avatars")
                    flash("Ошибка при сохранении в базу.", "danger")

            except Exception as exc:
                logger.error("Ошибка аватара: %s", exc)
                flash(f"Не удалось сохранить изображение: {exc}", "danger")

        return redirect(url_for("main.profile"))

    elif request.method == "POST":
        flash("Ошибка при загрузке аватара. Проверьте формат и размер файла.", "warning")

    return render_template("profile.html", title="Мой профиль", avatar_form=avatar_form, stats=stats)


@main.route("/subjects", methods=["GET", "POST"])
@login_required
def subjects():
    form = SubjectForm()
    delete_form = DeleteForm()

    if form.validate_on_submit():
        new_subject = Subject(
            name=form.name.data.strip(),
            target_score=form.target_score.data,
            color=form.color.data,
            user_id=current_user.id,
        )
        db.session.add(new_subject)

        if _commit_or_rollback("добавление предмета"):
            logger.info("Предмет добавлен: id=%d, name='%s', user_id=%d", new_subject.id, new_subject.name, current_user.id)
            flash(f"📚 Предмет «{new_subject.name}» успешно добавлен! Теперь добавь первую задачу.", "success")
            return redirect(url_for("main.subjects"))
        else:
            flash("Не удалось сохранить предмет. Попробуйте ещё раз.", "danger")

    user_subjects = (
        Subject.query
        .filter_by(user_id=current_user.id)
        .order_by(Subject.created_at.desc())
        .all()
    )

    return render_template(
        "subjects.html",
        title="Мои предметы",
        form=form,
        subjects=user_subjects,
        delete_form=delete_form,
    )


@main.route("/subjects/<int:subject_id>/edit", methods=["GET", "POST"])
@login_required
def edit_subject(subject_id: int):
    subject = _get_subject_or_404(subject_id)
    form = SubjectForm(obj=subject)

    if form.validate_on_submit():
        subject.name = form.name.data.strip()
        subject.target_score = form.target_score.data
        subject.color = form.color.data

        if _commit_or_rollback("редактирование предмета"):
            logger.info("Предмет обновлён: id=%d, name='%s', user_id=%d", subject.id, subject.name, current_user.id)
            flash(f"✅ Предмет «{subject.name}» успешно обновлён.", "success")
            return redirect(url_for("main.subjects"))
        else:
            flash("Не удалось сохранить изменения. Попробуйте ещё раз.", "danger")

    return render_template("edit_subject.html", title=f"Редактировать: {subject.name}", form=form, subject=subject)


@main.route("/subjects/<int:subject_id>/delete", methods=["POST"])
@login_required
def delete_subject(subject_id: int):
    delete_form = DeleteForm()

    if not delete_form.validate_on_submit():
        flash("Некорректный запрос удаления (ошибка CSRF). Попробуйте ещё раз через форму.", "warning")
        return redirect(url_for("main.subjects"))

    subject = _get_subject_or_404(subject_id)
    subject_name = subject.name

    files_to_delete = [
        task_file.stored_filename
        for task in subject.tasks
        for task_file in task.files
    ]

    db.session.delete(subject)

    if _commit_or_rollback("удаление предмета"):
        deleted_count = sum(
            1 for f in files_to_delete if delete_file_from_disk(f, subfolder="task_files")
        )
        logger.info(
            "Предмет удалён: name='%s', user_id=%d, файлов удалено: %d/%d",
            subject_name, current_user.id, deleted_count, len(files_to_delete),
        )
        flash(f"🗑️ Предмет «{subject_name}» и все его задачи удалены.", "success")
    else:
        flash(f"Не удалось удалить предмет «{subject_name}». Попробуйте ещё раз.", "danger")

    return redirect(url_for("main.subjects"))


@main.route("/subjects/<int:subject_id>/tasks/add", methods=["GET", "POST"])
@login_required
def add_task(subject_id: int):
    subject = _get_subject_or_404(subject_id)
    form = TaskForm()

    if form.validate_on_submit():
        due_datetime = None
        if form.due_date.data:
            due_datetime = datetime(
                form.due_date.data.year,
                form.due_date.data.month,
                form.due_date.data.day,
                23, 59, 59,
                tzinfo=timezone.utc,
            )

        new_task = Task(
            title=form.title.data.strip(),
            description=form.description.data.strip() if form.description.data else None,
            priority=form.priority.data,
            due_date=due_datetime,
            subject_id=subject.id,
        )
        db.session.add(new_task)
        db.session.flush()

        file_saved_successfully = True
        file_storage = form.file.data

        if file_storage and file_storage.filename and file_storage.filename.strip():
            if not is_allowed_file(file_storage.filename):
                flash(f"⚠️ Файл '{file_storage.filename}' имеет недопустимый формат и не был прикреплён.", "warning")
                file_saved_successfully = False
            else:
                try:
                    original_name, stored_name, file_size = save_uploaded_file(file_storage, subfolder="task_files")
                    db.session.add(TaskFile(
                        original_filename=original_name,
                        stored_filename=stored_name,
                        file_size=file_size,
                        task_id=new_task.id,
                    ))
                except Exception as exc:
                    logger.error("Ошибка при сохранении файла для задачи: %s", exc)
                    flash(f"⚠️ Задача создана, но файл не сохранен: {exc}", "warning")
                    file_saved_successfully = False

        if _commit_or_rollback("создание задачи"):
            logger.info("Задача создана: id=%d, title='%s', file=%s", new_task.id, new_task.title, file_saved_successfully)
            if file_saved_successfully and file_storage and file_storage.filename:
                flash(f"✅ Задача «{new_task.title}» добавлена с файлом!", "success")
            else:
                flash(f"✅ Задача «{new_task.title}» успешно добавлена!", "success")
            return redirect(url_for("main.subjects"))
        else:
            flash("Критическая ошибка БД при сохранении задачи.", "danger")

    return render_template("add_task.html", title=f"Новая задача — {subject.name}", form=form, subject=subject)


@main.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit_task(task_id: int):
    task = _get_task_or_404(task_id)
    form = TaskForm(obj=task)

    if request.method == "GET" and task.due_date:
        form.due_date.data = task.due_date.date()

    if form.validate_on_submit():
        task.title = form.title.data.strip()
        task.description = form.description.data.strip() if form.description.data else None
        task.priority = form.priority.data
        task.due_date = (
            datetime(
                form.due_date.data.year,
                form.due_date.data.month,
                form.due_date.data.day,
                23, 59, 59,
                tzinfo=timezone.utc,
            )
            if form.due_date.data else None
        )

        file_storage = form.file.data
        if file_storage and file_storage.filename and file_storage.filename.strip():
            if not is_allowed_file(file_storage.filename):
                flash(
                    f"⚠️ Недопустимый формат файла: '{file_storage.filename}'. "
                    "Разрешены только: pdf, png, jpg, jpeg, gif.",
                    "danger",
                )
            else:
                try:
                    for old_file in task.files:
                        delete_file_from_disk(old_file.stored_filename, subfolder="task_files")
                        db.session.delete(old_file)

                    original_name, stored_name, file_size = save_uploaded_file(file_storage, subfolder="task_files")
                    db.session.add(TaskFile(
                        original_filename=original_name,
                        stored_filename=stored_name,
                        file_size=file_size,
                        task_id=task.id,
                    ))
                    logger.info("Файл задачи обновлён: %s", original_name)
                except Exception as exc:
                    logger.error("Ошибка при обновлении файла: %s", exc)
                    flash(f"⚠️ Файл не был обновлён: {exc}", "warning")

        elif form.delete_file.data:
            try:
                for old_file in task.files:
                    delete_file_from_disk(old_file.stored_filename, subfolder="task_files")
                    db.session.delete(old_file)
            except OSError as exc:
                logger.error("Ошибка при удалении файла задачи id=%d: %s", task.id, exc)
                flash("Не удалось удалить файл с диска.", "warning")

        if _commit_or_rollback("редактирование задачи"):
            flash(f"✅ Задача «{task.title}» успешно обновлена.", "success")
            return redirect(url_for("main.subjects"))
        else:
            flash("Не удалось сохранить изменения задачи.", "danger")

    return render_template("edit_task.html", title="Редактировать задачу", form=form, task=task)


@main.route("/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle_task(task_id: int):
    csrf_form = DeleteForm()

    if not csrf_form.validate_on_submit():
        flash("Некорректный запрос (ошибка CSRF).", "warning")
        return redirect(url_for("main.dashboard"))

    task = _get_task_or_404(task_id)
    new_status = task.toggle_done()

    if _commit_or_rollback("переключение статуса задачи"):
        logger.info("Статус задачи: id=%d, is_done=%s, user_id=%d", task.id, new_status, current_user.id)
        if new_status:
            flash(f"🎉 Задача «{task.title}» выполнена! Отличная работа!", "success")
        else:
            flash(f"↩️ Задача «{task.title}» возвращена в список невыполненных.", "info")
    else:
        flash("Не удалось обновить статус задачи.", "danger")

    referer = request.referrer
    if referer and referer.startswith(request.host_url):
        return redirect(referer)
    return redirect(url_for("main.dashboard"))


@main.route("/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(task_id: int):
    delete_form = DeleteForm()

    if not delete_form.validate_on_submit():
        flash("Некорректный запрос удаления (ошибка CSRF).", "warning")
        return redirect(url_for("main.dashboard"))

    task = _get_task_or_404(task_id)
    task_title = task.title

    # Собираем имена файлов ДО удаления из БД
    files_to_delete = [task_file.stored_filename for task_file in task.files]

    db.session.delete(task)

    if _commit_or_rollback("удаление задачи"):
        for stored_filename in files_to_delete:
            delete_file_from_disk(stored_filename, subfolder="task_files")
        logger.info("Задача удалена: title='%s', user_id=%d, файлов: %d", task_title, current_user.id, len(files_to_delete))
        flash(f"🗑️ Задача «{task_title}» удалена.", "success")
    else:
        flash(f"Не удалось удалить задачу «{task_title}».", "danger")

    referer = request.referrer
    if referer and referer.startswith(request.host_url):
        return redirect(referer)
    return redirect(url_for("main.subjects"))


@main.route("/files/<path:filename>")
@login_required
def serve_file(filename: str):
    upload_folder = current_app.config["UPLOAD_FOLDER"]
    safe_path = os.path.normpath(filename)
    full_path = os.path.join(upload_folder, safe_path)

    # Защита от path traversal (не даём выйти за пределы UPLOAD_FOLDER)
    if not full_path.startswith(os.path.abspath(upload_folder)):
        logger.warning("Попытка path traversal: filename='%s', user_id=%d", filename, current_user.id)
        abort(403)

    if not os.path.exists(full_path):
        logger.warning("Файл не найден: '%s'", full_path)
        abort(404)

    return send_from_directory(os.path.dirname(full_path), os.path.basename(full_path), as_attachment=False)


@main.route("/antistress")
@login_required
def antistress():
    logger.info("Антистресс: user_id=%d", current_user.id)
    result = fetch_random_dog_image()

    wants_json = (
        "application/json" in request.headers.get("Accept", "")
        or request.args.get("format") == "json"
    )

    if wants_json:
        return jsonify(result)

    if not result["success"]:
        flash(f"🐶 Не удалось загрузить картинку: {result['message']}", "danger")
    else:
        flash("🐶 Вот тебе хорошая собачка — всё будет хорошо!", "info")

    return render_template("antistress.html", title="Антистресс", dog_result=result)


@main.app_errorhandler(403)
def forbidden(error):
    logger.warning("403 Forbidden: %s", request.url)
    return render_template("errors/403.html", title="403 — Доступ запрещён"), 403


@main.app_errorhandler(404)
def not_found(error):
    logger.warning("404 Not Found: %s", request.url)
    return render_template("errors/404.html", title="404 — Страница не найдена"), 404


@main.app_errorhandler(413)
def request_entity_too_large(error):
    logger.warning(
        "413 File Too Large от user_id=%s: %s",
        current_user.id if current_user.is_authenticated else "anonymous",
        request.url,
    )
    flash("Загружаемый файл слишком большой. Максимальный размер — 16 МБ.", "danger")
    return render_template("errors/413.html", title="413 — Файл слишком большой"), 413


@main.app_errorhandler(500)
def internal_server_error(error):
    db.session.rollback()
    logger.error("500 Internal Server Error: %s — %s", request.url, error)
    return render_template("errors/500.html", title="500 — Внутренняя ошибка сервера"), 500