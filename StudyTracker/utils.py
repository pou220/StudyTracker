import os
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

import requests
from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

logger = logging.getLogger("study_tracker.utils")

DOG_API_URL = "https://dog.ceo/api/breeds/image/random"
REQUEST_TIMEOUT = (5, 10)
MAX_RETRY_ATTEMPTS = 2
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def is_allowed_file(filename: str) -> bool:
    if not filename:
        return False
    _, ext = os.path.splitext(filename)
    return ext.lower().lstrip(".") in ALLOWED_EXTENSIONS


def generate_unique_filename(original_filename: str) -> str:
    if "." not in original_filename:
        raise ValueError(
            f"Файл '{original_filename}' не имеет расширения. "
            "Загрузка файлов без расширения запрещена."
        )
    ext = original_filename.rsplit(".", 1)[1].lower()
    return f"{uuid.uuid4()}.{ext}"


def save_uploaded_file(file_storage: FileStorage, subfolder: str = "") -> tuple[str, str, int]:
    if not file_storage or not file_storage.filename:
        raise ValueError("Получен пустой объект файла.")

    safe_original = secure_filename(file_storage.filename)
    if not safe_original or "." not in safe_original:
        if "." in file_storage.filename:
            ext = file_storage.filename.rsplit(".", 1)[1].lower()
            safe_original = f"file.{ext}"
        else:
            raise ValueError(
                "Имя файла содержит только недопустимые символы. "
                "Переименуйте файл, используя латинские буквы."
            )

    stored_filename = generate_unique_filename(safe_original)
    upload_base = current_app.config["UPLOAD_FOLDER"]
    target_dir = os.path.join(upload_base, subfolder) if subfolder else upload_base
    os.makedirs(target_dir, exist_ok=True)

    file_path = os.path.join(target_dir, stored_filename)
    file_storage.save(file_path)
    file_size = os.path.getsize(file_path)

    logger.info("Файл сохранён: '%s' -> '%s' (%d bytes)", safe_original, stored_filename, file_size)
    return safe_original, stored_filename, file_size


def delete_file_from_disk(stored_filename: str, subfolder: str = "") -> bool:
    upload_base = current_app.config["UPLOAD_FOLDER"]
    file_path = (
        os.path.join(upload_base, subfolder, stored_filename)
        if subfolder
        else os.path.join(upload_base, stored_filename)
    )

    if not os.path.exists(file_path):
        logger.warning("Попытка удалить несуществующий файл: '%s'", file_path)
        return False

    try:
        os.remove(file_path)
        logger.info("Файл удалён: '%s'", file_path)
        return True
    except OSError as exc:
        logger.error("Ошибка при удалении файла '%s': %s", file_path, exc)
        return False


def get_file_url_path(stored_filename: str, subfolder: str = "") -> str:
    return f"uploads/{subfolder}/{stored_filename}" if subfolder else f"uploads/{stored_filename}"


def fetch_random_dog_image() -> dict:
    logger.debug("Запрос к Dog API: %s", DOG_API_URL)

    for attempt in range(1, MAX_RETRY_ATTEMPTS + 1):
        try:
            response = _make_dog_api_request()
            return _parse_dog_api_response(response)

        except requests.exceptions.ConnectionError as exc:
            logger.warning("Dog API недоступен (попытка %d/%d): %s", attempt, MAX_RETRY_ATTEMPTS, exc)
            if attempt == MAX_RETRY_ATTEMPTS:
                return _build_error_response(
                    "Не удалось подключиться к Dog API. "
                    "Проверьте интернет-соединение и попробуйте снова."
                )

        except requests.exceptions.Timeout as exc:
            logger.warning("Dog API не ответил вовремя (попытка %d/%d): %s", attempt, MAX_RETRY_ATTEMPTS, exc)
            if attempt == MAX_RETRY_ATTEMPTS:
                return _build_error_response(
                    "Dog API слишком долго не отвечает. "
                    "Попробуйте нажать кнопку ещё раз чуть позже."
                )

        except requests.exceptions.HTTPError as exc:
            status_code = exc.response.status_code if exc.response else "?"
            logger.error("Dog API вернул HTTP-ошибку %s: %s", status_code, exc)
            return _build_error_response(
                f"Dog API вернул ошибку (код {status_code}). Сервис временно недоступен."
            )

        except requests.exceptions.RequestException as exc:
            logger.error("Непредвиденная ошибка при запросе к Dog API: %s", exc)
            return _build_error_response("Произошла непредвиденная сетевая ошибка. Попробуйте позже.")

    return _build_error_response("Исчерпаны все попытки запроса к Dog API.")


def _make_dog_api_request() -> requests.Response:
    response = requests.get(
        DOG_API_URL,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": "StudyTracker/1.0 (Educational Project)",
            "Accept": "application/json",
        },
    )
    response.raise_for_status()
    return response


def _parse_dog_api_response(response: requests.Response) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        logger.error("Dog API вернул не-JSON ответ: %s", exc)
        return _build_error_response("Dog API вернул некорректный ответ. Попробуйте позже.")

    if not isinstance(data, dict):
        logger.error("Dog API вернул неожиданный тип данных: %s", type(data))
        return _build_error_response("Неожиданный формат ответа от Dog API.")

    api_status = data.get("status")
    image_url = data.get("message")

    if api_status != "success":
        logger.warning("Dog API вернул статус '%s' вместо 'success'", api_status)
        return _build_error_response(f"Dog API сообщил об ошибке: статус '{api_status}'.")

    if not image_url or not isinstance(image_url, str):
        logger.error("Dog API не вернул URL изображения: %s", data)
        return _build_error_response("Dog API не вернул ссылку на изображение.")

    if not image_url.startswith("https://"):
        logger.warning("Dog API вернул небезопасный URL: %s", image_url)
        return _build_error_response("Dog API вернул небезопасный URL изображения.")

    logger.info("Dog API вернул изображение: %s", image_url)
    return {"success": True, "image_url": image_url, "message": "Держи собачку — это лучший антистресс! 🐶"}


def _build_error_response(user_message: str) -> dict:
    return {"success": False, "image_url": None, "message": user_message}


def format_datetime_ru(dt: Optional[datetime]) -> str:
    if dt is None:
        return "—"
    months = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря",
    }
    return f"{dt.day} {months[dt.month]} {dt.year}, {dt.hour:02d}:{dt.minute:02d}"


def calculate_dashboard_stats(user) -> dict:
    all_tasks = [task for subject in user.subjects for task in subject.tasks]
    total = len(all_tasks)
    completed = sum(1 for t in all_tasks if t.is_done)

    return {
        "total_subjects": len(user.subjects),
        "total_tasks": total,
        "completed_tasks": completed,
        "pending_tasks": total - completed,
        "overdue_tasks": sum(1 for t in all_tasks if t.is_overdue()),
        "progress_percent": int(completed / total * 100) if total else 0,
        "high_priority_tasks": sum(1 for t in all_tasks if t.priority == "high" and not t.is_done),
    }


def register_template_filters(app) -> None:
    @app.template_filter("datetime_ru")
    def _datetime_ru_filter(dt: Optional[datetime]) -> str:
        return format_datetime_ru(dt)

    @app.template_filter("file_url")
    def _file_url_filter(stored_filename: str, subfolder: str = "") -> str:
        return get_file_url_path(stored_filename, subfolder) if stored_filename else ""