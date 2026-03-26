from datetime import date
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileSize
from wtforms import (
    StringField,
    PasswordField,
    SubmitField,
    BooleanField,
    TextAreaField,
    SelectField,
    DateField,
    IntegerField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    NumberRange,
    Optional,
    Regexp,
    ValidationError,
)
from models import User


USERNAME_MIN_LEN = 3
USERNAME_MAX_LEN = 80
PASSWORD_MIN_LEN = 6
PASSWORD_MAX_LEN = 128
SUBJECT_NAME_MAX_LEN = 100
TASK_TITLE_MAX_LEN = 200
TASK_DESCRIPTION_MAX_LEN = 2000
TARGET_SCORE_MIN = 0
TARGET_SCORE_MAX = 100

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
MAX_FILE_SIZE_MB = 5

ALLOWED_FILE_EXTENSIONS = ("png", "jpg", "jpeg", "gif", "pdf")
ALLOWED_AVATAR_EXTENSIONS = ("png", "jpg", "jpeg", "gif")

SUBJECT_COLOR_CHOICES = [
    ("#0d6efd", "Синий"),
    ("#198754", "Зелёный"),
    ("#dc3545", "Красный"),
    ("#ffc107", "Жёлтый"),
    ("#6f42c1", "Фиолетовый"),
    ("#0dcaf0", "Голубой"),
    ("#fd7e14", "Оранжевый"),
    ("#6c757d", "Серый"),
]

PRIORITY_CHOICES = [
    ("low", "🟢 Низкий"),
    ("medium", "🟡 Средний"),
    ("high", "🔴 Высокий"),
]


class RegistrationForm(FlaskForm):
    username = StringField(
        label="Имя пользователя",
        validators=[
            DataRequired(message="Имя пользователя обязательно."),
            Length(
                min=USERNAME_MIN_LEN,
                max=USERNAME_MAX_LEN,
                message=(
                    f"Имя пользователя должно содержать от "
                    f"{USERNAME_MIN_LEN} до {USERNAME_MAX_LEN} символов."
                ),
            ),
            # Защита от XSS-подобных атак через имя пользователя (кириллица разрешена)
            Regexp(
                r"^[\w\u0400-\u04FF]+$",
                message=(
                    "Имя пользователя может содержать только буквы, "
                    "цифры и символ подчёркивания (_)."
                ),
            ),
        ],
        render_kw={"placeholder": "например, ivan_petrov"},
    )

    email = StringField(
        label="Email",
        validators=[
            DataRequired(message="Email обязателен."),
            Email(message="Введите корректный email-адрес."),
            Length(max=120, message="Email не может быть длиннее 120 символов."),
        ],
        render_kw={"placeholder": "ivan@example.com"},
    )

    password = PasswordField(
        label="Пароль",
        validators=[
            DataRequired(message="Пароль обязателен."),
            Length(
                min=PASSWORD_MIN_LEN,
                max=PASSWORD_MAX_LEN,
                message=(
                    f"Пароль должен содержать от {PASSWORD_MIN_LEN} "
                    f"до {PASSWORD_MAX_LEN} символов."
                ),
            ),
        ],
        render_kw={"placeholder": f"Минимум {PASSWORD_MIN_LEN} символов"},
    )

    confirm_password = PasswordField(
        label="Подтвердите пароль",
        validators=[
            DataRequired(message="Подтверждение пароля обязательно."),
            EqualTo("password", message="Пароли не совпадают. Проверьте введённые данные."),
        ],
        render_kw={"placeholder": "Повторите пароль"},
    )

    target_university = SelectField(
        label="Целевой ВУЗ",
        choices=[
            ("МИФИ", "МИФИ"),
            ("СГТУ", "СГТУ"),
            ("СГУ", "СГУ"),
            ("РАНХиГС", "РАНХиГС"),
            ("Другой", "Другой"),
        ],
        validators=[DataRequired()],
    )

    other_university = StringField(
        label="Укажите ваш ВУЗ",
        validators=[Length(max=100)],
        render_kw={"placeholder": "Например, МГТУ им. Баумана"},
    )

    submit = SubmitField(label="Зарегистрироваться")

    def validate_username(self, username: StringField) -> None:
        if User.query.filter_by(username=username.data).first():
            raise ValidationError(
                f"Имя пользователя «{username.data}» уже занято. "
                "Пожалуйста, выберите другое."
            )

    def validate_email(self, email: StringField) -> None:
        if User.query.filter_by(email=email.data).first():
            raise ValidationError(
                "Этот email уже зарегистрирован. "
                "Войдите в существующий аккаунт или используйте другой email."
            )

    def validate_password(self, password: PasswordField) -> None:
        pwd = password.data or ""
        if " " in pwd:
            raise ValidationError("Пароль не должен содержать пробелы.")
        if not any(char.isdigit() for char in pwd):
            raise ValidationError("Пароль должен содержать хотя бы одну цифру.")

    def validate_other_university(self, field) -> None:
        if self.target_university.data == "Другой" and not field.data.strip():
            raise ValidationError("Пожалуйста, укажите ваш ВУЗ.")


class LoginForm(FlaskForm):
    email = StringField(
        label="Email",
        validators=[
            DataRequired(message="Введите email."),
            Email(message="Некорректный формат email."),
        ],
        render_kw={"placeholder": "ivan@example.com", "autofocus": True},
    )

    password = PasswordField(
        label="Пароль",
        validators=[DataRequired(message="Введите пароль.")],
        render_kw={"placeholder": "Ваш пароль"},
    )

    remember_me = BooleanField(label="Запомнить меня")
    submit = SubmitField(label="Войти")


class SubjectForm(FlaskForm):
    name = StringField(
        label="Название предмета",
        validators=[
            DataRequired(message="Название предмета обязательно."),
            Length(
                max=SUBJECT_NAME_MAX_LEN,
                message=f"Название не может превышать {SUBJECT_NAME_MAX_LEN} символов.",
            ),
        ],
        render_kw={"placeholder": "например, Информатика"},
    )

    target_score = IntegerField(
        label="Целевой балл ЕГЭ",
        validators=[
            Optional(),
            NumberRange(
                min=TARGET_SCORE_MIN,
                max=TARGET_SCORE_MAX,
                message=f"Балл ЕГЭ должен быть в диапазоне {TARGET_SCORE_MIN}–{TARGET_SCORE_MAX}.",
            ),
        ],
        render_kw={"placeholder": "от 0 до 100"},
    )

    color = SelectField(
        label="Цвет метки",
        choices=SUBJECT_COLOR_CHOICES,
        default="#0d6efd",
        validators=[DataRequired(message="Выберите цвет.")],
    )

    submit = SubmitField(label="Сохранить предмет")

    def validate_target_score(self, target_score: IntegerField) -> None:
        # Балл ниже 20 бессмысленен для ЕГЭ (предупреждаем, чтобы не путать с пустым полем)
        if target_score.data is not None and target_score.data < 20:
            raise ValidationError(
                "Целевой балл ниже 20 не имеет смысла для ЕГЭ. "
                "Оставьте поле пустым, если цель ещё не определена."
            )


class TaskForm(FlaskForm):
    title = StringField(
        label="Название задачи",
        validators=[
            DataRequired(message="Название задачи обязательно."),
            Length(
                max=TASK_TITLE_MAX_LEN,
                message=f"Название не может превышать {TASK_TITLE_MAX_LEN} символов.",
            ),
        ],
        render_kw={"placeholder": "например, Решить вариант №5 (Ященко)"},
    )

    description = TextAreaField(
        label="Описание (необязательно)",
        validators=[
            Optional(),
            Length(
                max=TASK_DESCRIPTION_MAX_LEN,
                message=f"Описание не может превышать {TASK_DESCRIPTION_MAX_LEN} символов.",
            ),
        ],
        render_kw={"placeholder": "Подробности, номера заданий, ссылки...", "rows": 4},
    )

    priority = SelectField(
        label="Приоритет",
        choices=PRIORITY_CHOICES,
        default="medium",
        validators=[DataRequired(message="Выберите приоритет.")],
    )

    due_date = DateField(
        label="Дедлайн (необязательно)",
        validators=[Optional()],
        render_kw={"type": "date"},
    )

    file = FileField(
        label=f"Прикрепить файл (необязательно, макс. {MAX_FILE_SIZE_MB} МБ)",
        validators=[
            Optional(),
            FileAllowed(
                ALLOWED_FILE_EXTENSIONS,
                message=f"Разрешены только файлы форматов: {', '.join(ALLOWED_FILE_EXTENSIONS).upper()}.",
            ),
            FileSize(
                max_size=MAX_FILE_SIZE_BYTES,
                message=f"Размер файла не должен превышать {MAX_FILE_SIZE_MB} МБ.",
            ),
        ],
    )

    delete_file = BooleanField(label="Удалить текущий файл", validators=[Optional()])
    submit = SubmitField(label="Сохранить задачу")

    def validate_due_date(self, due_date: DateField) -> None:
        if due_date.data and due_date.data < date.today():
            raise ValidationError(
                "Дедлайн не может быть в прошлом. "
                "Выберите сегодняшнюю или будущую дату, или оставьте поле пустым."
            )


class AvatarUploadForm(FlaskForm):
    avatar = FileField(
        label="Выберите изображение",
        validators=[
            DataRequired(message="Выберите файл для загрузки."),
            FileAllowed(
                ALLOWED_AVATAR_EXTENSIONS,
                message=(
                    "Для аватара разрешены только изображения: "
                    f"{', '.join(ALLOWED_AVATAR_EXTENSIONS).upper()}."
                ),
            ),
            FileSize(
                max_size=MAX_FILE_SIZE_BYTES,
                message=f"Размер аватара не должен превышать {MAX_FILE_SIZE_MB} МБ.",
            ),
        ],
    )

    submit = SubmitField(label="Загрузить аватар")


class DeleteForm(FlaskForm):
    submit = SubmitField(label="Удалить")


class UpdateGoalForm(FlaskForm):
    target_university = SelectField(
        label="Целевой ВУЗ",
        choices=[
            ("МИФИ", "МИФИ"),
            ("СГТУ", "СГТУ"),
            ("СГУ", "СГУ"),
            ("РАНХиГС", "РАНХиГС"),
            ("Другой", "Другой"),
        ],
        validators=[DataRequired()],
    )

    other_university = StringField(
        label="Укажите ваш ВУЗ",
        validators=[Optional(), Length(max=100)],
        render_kw={"placeholder": "Например, МГТУ им. Баумана"},
    )

    submit = SubmitField(label="Сохранить цель")

    def validate_other_university(self, field) -> None:
        if self.target_university.data == "Другой" and not field.data.strip():
            raise ValidationError("Пожалуйста, укажите ваш ВУЗ.")