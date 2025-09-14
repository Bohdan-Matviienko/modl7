from collections import UserDict
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict, Tuple, Callable
import functools


# ============================
# Базові поля та валідація
# ============================

class Field:
    """Базовий клас для полів запису (має лише value)."""
    def __init__(self, value: str):
        self.value = value

    def __str__(self) -> str:
        return str(self.value)


class Name(Field):
    """Ім'я — без додаткової валідації."""
    pass


class Phone(Field):
    """Телефон — рівно 10 цифр, без інших символів."""
    def __init__(self, value: str):
        raw = value.strip()
        if not (raw.isdigit() and len(raw) == 10):
            raise ValueError("Номер телефону має складатися рівно з 10 цифр.")
        super().__init__(raw)


class Birthday(Field):
    """
    День народження у форматі DD.MM.YYYY.
    Клас має лише поле value (рядок). Валідація і нормалізація під час ініціалізації.
    """
    def __init__(self, value: str):
        try:
            dt = datetime.strptime(value.strip(), "%d.%m.%Y").date()
        except ValueError:
            raise ValueError("Invalid date format. Use DD.MM.YYYY")
        normalized = dt.strftime("%d.%m.%Y")
        super().__init__(normalized)


# ============================
# Запис і адресна книга
# ============================

class Record:
    """
    Один контакт: ім'я, список телефонів, опційно день народження.
    """
    def __init__(self, name: str):
        self.name = Name(name)
        self.phones: List[Phone] = []
        self.birthday: Optional[Birthday] = None

    # --- робота з телефонами ---
    def add_phone(self, phone: str) -> None:
        p = Phone(phone)
        if any(ph.value == p.value for ph in self.phones):
            return
        self.phones.append(p)

    def remove_phone(self, phone: str) -> None:
        cleaned = Phone(phone).value  # перевірка формату + нормалізація
        for i, ph in enumerate(self.phones):
            if ph.value == cleaned:
                del self.phones[i]
                return
        raise ValueError("Цього номеру немає у контакті.")

    def edit_phone(self, old: str, new: str) -> None:
        old_clean = Phone(old).value
        new_phone = Phone(new)
        for ph in self.phones:
            if ph.value == old_clean:
                ph.value = new_phone.value
                return
        raise ValueError("Старий номер не знайдено у контакті.")

    # --- робота з днем народження ---
    def add_birthday(self, birthday_str: str) -> None:
        if self.birthday is not None:
            raise ValueError("День народження вже задано для цього контакту.")
        self.birthday = Birthday(birthday_str)

    def birthday_str(self) -> Optional[str]:
        return str(self.birthday) if self.birthday else None

    def __str__(self) -> str:
        phones = ", ".join(ph.value for ph in self.phones) if self.phones else "—"
        bday = self.birthday.value if self.birthday else "—"
        return f"{self.name.value}: phones [{phones}] | birthday [{bday}]"


class AddressBook(UserDict):
    """
    Адресна книга з пошуком/додаванням записів + метод get_upcoming_birthdays.
    data: Dict[str, Record], ключ — ім'я у первісному регістрі.
    """
    def add_record(self, record: Record) -> None:
        self.data[record.name.value] = record

    def find(self, name: str) -> Optional[Record]:
        return self.data.get(name)

    def delete(self, name: str) -> None:
        if name in self.data:
            del self.data[name]
        else:
            raise KeyError("Контакт з таким іменем не знайдено.")

    # ---- Головний метод з автоперевірки (тиждень 3) ----
    def get_upcoming_birthdays(self, days: int = 7) -> List[Dict[str, str]]:
        """
        Повертає список словників {"name": Ім'я, "birthday": Дата-привітання у форматі DD.MM.YYYY}
        для днів народження, які трапляються протягом наступних `days` днів включно з сьогодні.
        Якщо ДН на вихідних — переносимо привітання на найближчий понеділок.
        """
        today = date.today()
        end_date = today + timedelta(days=days - 1)

        result: List[Dict[str, str]] = []

        for rec in self.data.values():
            if not rec.birthday:
                continue

            # Парсимо з value щоразу (у класі Birthday зберігаємо тільки value)
            bday = datetime.strptime(rec.birthday.value, "%d.%m.%Y").date()

            bday_this_year = bday.replace(year=today.year)
            if bday_this_year < today:
                bday_this_year = bday_this_year.replace(year=today.year + 1)

            if today <= bday_this_year <= end_date:
                greet_date = self._shift_if_weekend(bday_this_year)
                result.append({
                    "name": rec.name.value,
                    "birthday": greet_date.strftime("%d.%m.%Y")
                })

        result.sort(key=lambda x: datetime.strptime(x["birthday"], "%d.%m.%Y").date())
        return result

    @staticmethod
    def _shift_if_weekend(d: date) -> date:
        # 5 = Saturday, 6 = Sunday
        if d.weekday() == 5:
            return d + timedelta(days=2)
        if d.weekday() == 6:
            return d + timedelta(days=1)
        return d


# ============================
# Інфраструктура CLI
# ============================

def input_error(func: Callable) -> Callable:
    """Декоратор для дружніх повідомлень про помилки."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except IndexError:
            return "Недостатньо аргументів для команди."
        except AttributeError:
            # Напр., record = None → спроба доступу до атрибутів/методів
            return "Контакт не знайдено."
        except KeyError as e:
            return str(e) if str(e) else "Не знайдено."
        except ValueError as e:
            return str(e)
        except Exception as e:
            return f"Сталася помилка: {e}"
    return wrapper


def parse_input(user_input: str) -> Tuple[str, List[str]]:
    user_input = user_input.strip()
    if not user_input:
        return "", []
    parts = user_input.split()
    command = parts[0].lower()
    args = parts[1:]
    return command, args


# ============================
# Хендлери команд
# ============================

@input_error
def add_contact(args: List[str], book: AddressBook) -> str:
    name, phone, *_ = args
    record = book.find(name)
    message = "Contact updated."
    if record is None:
        record = Record(name)
        book.add_record(record)
        message = "Contact added."
    if phone:
        record.add_phone(phone)
    return message


@input_error
def change_phone(args: List[str], book: AddressBook) -> str:
    name, old_phone, new_phone, *_ = args
    record = book.find(name)
    record.edit_phone(old_phone, new_phone)  # якщо record=None → AttributeError → декоратор
    return "Phone changed."


@input_error
def show_phone(args: List[str], book: AddressBook) -> str:
    name, *_ = args
    record = book.find(name)
    if not record.phones:  # якщо record=None → AttributeError → декоратор
        return "У контакту немає телефонів."
    return ", ".join(ph.value for ph in record.phones)


@input_error
def show_all(_: List[str], book: AddressBook) -> str:
    if not book.data:
        return "Адресна книга порожня."
    lines = []
    for rec in book.values():
        phones = ", ".join(ph.value for ph in rec.phones) if rec.phones else "—"
        bday = rec.birthday.value if rec.birthday else "—"
        lines.append(f"{rec.name.value}: {phones}; birthday: {bday}")
    return "\n".join(lines)


@input_error
def add_birthday(args: List[str], book: AddressBook) -> str:
    name, bday_str, *_ = args
    record = book.find(name)
    record.add_birthday(bday_str)  # якщо record=None → AttributeError → декоратор
    return "Birthday added."


@input_error
def show_birthday(args: List[str], book: AddressBook) -> str:
    name, *_ = args
    record = book.find(name)
    if not record.birthday:  # якщо record=None → AttributeError → декоратор
        return "Для цього контакту не задано дня народження."
    return record.birthday.value


@input_error
def birthdays(args: List[str], book: AddressBook) -> str:
    upcoming = book.get_upcoming_birthdays(days=7)
    if not upcoming:
        return "Найближчими 7 днями іменин немає."

    by_date: Dict[str, List[str]] = {}
    for item in upcoming:
        by_date.setdefault(item["birthday"], []).append(item["name"])

    def parse_d(d: str) -> date:
        return datetime.strptime(d, "%d.%m.%Y").date()

    lines = []
    for d_str in sorted(by_date.keys(), key=parse_d):
        names = ", ".join(sorted(by_date[d_str]))
        weekday = parse_d(d_str).strftime("%A")
        lines.append(f"{d_str} ({weekday}): {names}")
    return "\n".join(lines)


# ============================
# Головна петля
# ============================

def main():
    book = AddressBook()
    print("Welcome to the assistant bot!")
    while True:
        user_input = input("Enter a command: ").strip()
        if not user_input:
            continue

        command, args = parse_input(user_input)

        if command in ["close", "exit"]:
            print("Good bye!")
            break

        elif command == "hello":
            print("How can I help you?")

        elif command == "add":
            print(add_contact(args, book))

        elif command == "change":
            print(change_phone(args, book))

        elif command == "phone":
            print(show_phone(args, book))

        elif command == "all":
            print(show_all(args, book))

        elif command == "add-birthday":
            print(add_birthday(args, book))

        elif command == "show-birthday":
            print(show_birthday(args, book))

        elif command == "birthdays":
            print(birthdays(args, book))

        else:
            print("Invalid command.")


if __name__ == "__main__":
    main()
