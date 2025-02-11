import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Router, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from database.models import get_db
from states.user_states import UserStates
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
from aiogram.fsm.state import State, StatesGroup
import re
import logging
from aiogram.exceptions import TelegramBadRequest
import io

logging.basicConfig(level=logging.DEBUG)

router = Router()

class RegistrationStates(StatesGroup):
    waiting_for_phone = State()
    waiting_for_fullname = State()

class BookStates(StatesGroup):
    waiting_for_days = State() 
    waiting_for_extend_days = State()  

class SuggestBookStates(StatesGroup):
    waiting_for_title = State()
    waiting_for_url = State()
    waiting_for_price = State()
    waiting_for_reason = State()

class ReviewStates(StatesGroup):
    waiting_for_rating = State()
    waiting_for_text = State()

BOOKS_PER_PAGE = 5
MAX_BOOKS_PER_USER = 10

def validate_phone(phone: str) -> bool:
    """Проверяет корректность номера телефона"""
    return bool(re.match(r'^7\d{10}$', phone))

def get_main_keyboard():
    keyboard = [
        [
            types.KeyboardButton(text="📚 Каталог"),
            types.KeyboardButton(text="📚 Мои книги")
        ],
        [
            types.KeyboardButton(text="🔍 Поиск"),
            types.KeyboardButton(text="📝 Отзывы")
        ],
        [
            types.KeyboardButton(text="📖 Предложить книгу"),
            types.KeyboardButton(text="❓ Инструкция")
        ]
    ]
    
    return types.ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
        is_persistent=True
    )

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем, зарегистрирован ли пользователь
            cursor.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,))
            user = cursor.fetchone()
            
            if not user:
                await message.answer(
                    "👋 Добро пожаловать в библиотеку!\n"
                    "Для использования бота необходимо зарегистрироваться.\n"
                    "Пожалуйста, отправьте ваш номер телефона в формате: +7XXXXXXXXXX"
                )
                await state.set_state(RegistrationStates.waiting_for_phone)
            else:
                await message.answer(
                    "👋 С возвращением!\n"
                    "Используйте команду /menu чтобы узнать о доступных командах.",
                    reply_markup=get_main_keyboard()
                )
                
    except Exception as e:
        logging.error(f"Error in cmd_start: {e}")
        await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")

@router.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer(
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    )

@router.message(RegistrationStates.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = message.text.strip()
    
    # Простая проверка формата телефона
    if not (phone.startswith('+7') and len(phone) == 12 and phone[1:].isdigit()):
        await message.answer("❌ Неверный формат номера телефона. Пожалуйста, используйте формат: +7XXXXXXXXXX")
        return
        
    await state.update_data(phone=phone)
    await message.answer("Отлично! Теперь отправьте ваше полное имя (ФИО)")
    await state.set_state(RegistrationStates.waiting_for_fullname)

@router.message(RegistrationStates.waiting_for_fullname)
async def process_fullname(message: types.Message, state: FSMContext):
    full_name = message.text.strip()
    
    if len(full_name.split()) < 2:
        await message.answer("❌ Пожалуйста, введите полное имя (Фамилия Имя)")
        return
        
    user_data = await state.get_data()
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (id, username, full_name, phone)
                VALUES (?, ?, ?, ?)
            """, (
                message.from_user.id,
                message.from_user.username,
                full_name,
                user_data['phone']
            ))
            conn.commit()
            
        await state.clear()
        await message.answer(
            "✅ Регистрация успешно завершена!\n"
            "Используйте команду /menu чтобы узнать о доступных командах.",
            reply_markup=get_main_keyboard()
        )
        
    except Exception as e:
        logging.error(f"Error in process_fullname: {e}")
        await message.answer("Произошла ошибка при регистрации. Попробуйте позже.")

async def check_registration(message: types.Message) -> bool:
    try:
        with get_db() as conn:  # Правильное использование контекстного менеджера
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE id = ?", (message.from_user.id,))
            result = cursor.fetchone()
            
            if not result:
                await message.answer(
                    "❗️ Для использования этой функции необходимо зарегистрироваться.\n"
                    "Нажмите /start для регистрации."
                )
                return False
            return True
            
    except Exception as e:
        logging.error(f"Error checking registration: {e}")
        await message.answer("Произошла ошибка при проверке регистрации")
        return False

@router.message(F.text == "📚 Каталог")
async def catalog_command(message: types.Message):
    await show_catalog(message)

@router.callback_query(lambda c: c.data.startswith("catalog:"))
async def process_catalog_navigation(callback: types.CallbackQuery):
    try:
        page = int(callback.data.split(":")[1])
        await show_catalog(callback.message, page)
        await callback.answer()
    except Exception as e:
        logging.error(f"Error in catalog navigation: {e}")
        await callback.message.answer("Произошла ошибка при навигации")

async def show_catalog(message: types.Message, page: int = 1):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM books")
            total_books = cursor.fetchone()[0]
            total_pages = (total_books + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE
            
            cursor.execute("""
                SELECT id, title, author, description 
                FROM books 
                ORDER BY title
                LIMIT ? OFFSET ?
            """, (BOOKS_PER_PAGE, (page - 1) * BOOKS_PER_PAGE))
            
            books = cursor.fetchall()
            
            if not books:
                await message.answer("В каталоге пока нет книг")
                return
                
            text = f"📚 Каталог книг (страница {page} из {total_pages})"
            kb = InlineKeyboardBuilder()
            
            for book_id, title, author, description in books:
                kb.button(
                    text=f"{title} - {author}",
                    callback_data=f"book_info:{book_id}"
                )
            
            nav_buttons = []
            if page > 1:
                nav_buttons.append(("⬅️ Назад", f"catalog:{page-1}"))
            if page < total_pages:
                nav_buttons.append(("➡️ Вперед", f"catalog:{page+1}"))
            
            for btn_text, btn_data in nav_buttons:
                kb.button(text=btn_text, callback_data=btn_data)
            
            kb.adjust(1)
            
            if isinstance(message, types.Message):
                await message.answer(text, reply_markup=kb.as_markup())
            else:
                await message.edit_text(text, reply_markup=kb.as_markup())
            
    except Exception as e:
        logging.error(f"Error showing catalog: {e}")
        await message.answer("Произошла ошибка при загрузке каталога.")

@router.callback_query(F.data.startswith("book_info:"))
async def show_book_info(callback: types.CallbackQuery):
    try:
        book_id = int(callback.data.split(":")[1])
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем количество доступных (не списанных) копий
            cursor.execute("""
                SELECT COUNT(*) 
                FROM book_copies bc
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id AND bb.status IN ('booked', 'borrowed')
                WHERE bc.book_id = ? AND bc.status != 'written_off' AND bb.id IS NULL
            """, (book_id,))
            
            available_copies = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT COUNT(*) 
                FROM borrowed_books 
                WHERE user_id = ? AND status IN ('booked', 'borrowed')
            """, (callback.from_user.id,))
            user_books_count = cursor.fetchone()[0]
            
            cursor.execute("""
                SELECT 
                    b.title,
                    b.author,
                    b.description,
                    COUNT(DISTINCT bc.id) as total_copies,
                    COUNT(DISTINCT CASE WHEN bb.status IN ('booked', 'borrowed') THEN bc.id END) as busy_copies,
                    COALESCE(AVG(r.rating), 0) as avg_rating,
                    COUNT(DISTINCT r.id) as review_count
                FROM books b
                LEFT JOIN book_copies bc ON b.id = bc.book_id
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id AND bb.status IN ('booked', 'borrowed')
                LEFT JOIN book_reviews r ON b.id = r.book_id
                WHERE b.id = ?
                GROUP BY b.id
            """, (book_id,))
            
            book = cursor.fetchone()
            if not book:
                await callback.answer("Книга не найдена", show_alert=True)
                return
                
            title, author, description, total_copies, busy_copies, avg_rating, review_count = book
            available_copies = total_copies - busy_copies
            
            text = (
                f"📖 <b>{title}</b>\n"
                f"✍️ Автор: {author}\n\n"
                f"📝 Описание: {description}\n\n"
                f"📊 Статистика:\n"
                f"• Всего экземпляров: {total_copies}\n"
                f"• Доступно сейчас: {available_copies}\n"
                f"⭐️ Рейтинг: {avg_rating:.1f}/5 ({review_count} отзывов)\n"
            )
            
            # if available_copies > 0 and user_books_count < MAX_BOOKS_PER_USER:
            #     text += "\n❗️ У вас есть эта книга"
            if user_books_count >= MAX_BOOKS_PER_USER:
                text += f"\n❗️ Достигнут лимит книг ({MAX_BOOKS_PER_USER})"
            
            kb = InlineKeyboardBuilder()
            
            if available_copies > 0 and user_books_count < MAX_BOOKS_PER_USER:
                kb.button(
                    text="📝 Забронировать",
                    callback_data=f"borrow_{book_id}"
                )
            
            kb.button(
                text="✍️ Написать отзыв",
                callback_data=f"write_review:{book_id}"
            )
            
            kb.button(
                text="💬 Отзывы",
                callback_data=f"reviews:{book_id}"
            )
            
            kb.button(
                text="◀️ Назад к каталогу",
                callback_data="back_to_catalog"
            )
            
            kb.adjust(1)
            
            await callback.message.edit_text(
                text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
            
    except Exception as e:
        logging.error(f"Error in show_book_info: {e}")
        await callback.answer("Произошла ошибка при получении информации о книге", show_alert=True)

@router.callback_query(F.data == "back_to_catalog")
async def back_to_catalog(callback: types.CallbackQuery):
    await callback.message.delete()
    await show_catalog(callback.message)

@router.callback_query(F.data.startswith("reviews:"))
async def show_book_reviews(callback: types.CallbackQuery):
    try:
        book_id = callback.data.split(":")[1]
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT title, author
                FROM books
                WHERE id = ?
            """, (book_id,))
            
            book = cursor.fetchone()
            if not book:
                await callback.answer("Книга не найдена", show_alert=True)
                return
                
            title, author = book
            
            cursor.execute("""
                SELECT 
                    u.full_name,
                    r.rating,
                    r.review_text,
                    r.created_at
                FROM book_reviews r
                JOIN users u ON r.user_id = u.id
                WHERE r.book_id = ?
                ORDER BY r.created_at DESC
            """, (book_id,))
            
            reviews = cursor.fetchall()
            
            text = f"📖 Отзывы о книге\n<b>{title}</b>\n✍️ {author}\n\n"
            
            if not reviews:
                text += "Пока нет отзывов о книге."
            else:
                for review in reviews:
                    name, rating, review_text, date = review
                    stars = "⭐️" * rating
                    text += (
                        f"👤 {name}\n"
                        f"{stars}\n"
                        f"{review_text}\n"
                        f"📅 {date}\n\n"
                    )
            
            kb = InlineKeyboardBuilder()
            kb.button(text="◀️ Назад", callback_data=f"back_to_catalog")
            
            await callback.message.edit_text(
                text,
                reply_markup=kb.as_markup(),
                parse_mode="HTML"
            )
            
    except Exception as e:
        logging.error(f"Error in show_book_reviews: {e}")
        await callback.answer("Произошла ошибка при получении отзывов", show_alert=True)

@router.callback_query(F.data.startswith("borrow_"))
async def process_borrow(callback: types.CallbackQuery):
    try:
        book_id = int(callback.data.split("_")[1])
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем наличие доступных (не списанных) копий книги
            cursor.execute("""
                SELECT COUNT(*) 
                FROM book_copies bc
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id 
                    AND bb.status IN ('borrowed', 'booked')
                WHERE bc.book_id = ? 
                    AND bc.status != 'written_off'
                    AND bb.id IS NULL
            """, (book_id,))
            
            available_copies = cursor.fetchone()[0]
            
            if available_copies == 0:
                await callback.answer("❌ К сожалению, сейчас нет доступных экземпляров", show_alert=True)
                return
            
            # Получаем первую доступную копию
            cursor.execute("""
                SELECT bc.id
                FROM book_copies bc
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id 
                    AND bb.status IN ('borrowed', 'booked')
                WHERE bc.book_id = ? 
                    AND bc.status != 'written_off'
                    AND bb.id IS NULL
                LIMIT 1
            """, (book_id,))
            
            copy_id = cursor.fetchone()[0]
            
            # Создаем бронь
            cursor.execute("""
                INSERT INTO borrowed_books (user_id, copy_id, book_id, status, borrow_date)
                VALUES (?, ?, ?, 'booked', datetime('now'))
            """, (callback.from_user.id, copy_id, book_id))
            
            conn.commit()
            
            await callback.answer("✅ Книга успешно забронирована!", show_alert=True)
            
    except Exception as e:
        logging.error(f"Error in process_borrow: {e}")
        await callback.answer("❌ Произошла ошибка при бронировании", show_alert=True)

@router.callback_query(F.data.startswith("extend:"))
async def handle_extend_request(callback: types.CallbackQuery):
    try:
        borrow_id = callback.data.split(":")[1]
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    datetime(return_date) as return_date,
                    COALESCE(extended, 0) as extended
                FROM borrowed_books 
                WHERE id = ? AND status = 'borrowed'
            """, (borrow_id,))
            
            result = cursor.fetchone()
            if not result:
                await callback.answer("Книга не может быть продлена", show_alert=True)
                return
                
            return_date, extended = result
            
            if extended:
                await callback.answer(
                    "Книга уже была продлена один раз. Повторное продление невозможно.", 
                    show_alert=True
                )
                return
            
            kb = InlineKeyboardBuilder()
            kb.button(text="7 дней", callback_data=f"extend_confirm:{borrow_id}:7")
            kb.button(text="14 дней", callback_data=f"extend_confirm:{borrow_id}:14")
            kb.button(text="❌ Отмена", callback_data="cancel_extend")
            kb.adjust(2, 1)
            
            await callback.message.edit_text(
                "На сколько дней продлить книгу?\n"
                "⚠️ Продление возможно только один раз.",
                reply_markup=kb.as_markup()
            )
            
    except Exception as e:
        logging.error(f"Error in handle_extend_request: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("extend_confirm:"))
async def process_extend_days(callback: types.CallbackQuery):
    try:
        _, borrow_id, days = callback.data.split(":")
        days = int(days)
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    datetime(return_date) as return_date,
                    COALESCE(extended, 0) as extended
                FROM borrowed_books 
                WHERE id = ? AND status = 'borrowed'
            """, (borrow_id,))
            
            result = cursor.fetchone()
            if not result:
                await callback.answer("Книга не может быть продлена", show_alert=True)
                return
                
            current_return_date, extended = result
            
            if extended:
                await callback.answer(
                    "Книга уже была продлена один раз. Повторное продление невозможно.", 
                    show_alert=True
                )
                return
            
            # Продлеваем от текущей даты возврата
            current_return_datetime = datetime.strptime(current_return_date, '%Y-%m-%d %H:%M:%S')
            new_return_date = current_return_datetime + timedelta(days=days)
            
            cursor.execute("""
                UPDATE borrowed_books 
                SET return_date = datetime(?, 'localtime'),
                    extended = 1
                WHERE id = ? AND status = 'borrowed'
            """, (new_return_date.strftime("%Y-%m-%d %H:%M:%S"), borrow_id))
            
            conn.commit()
            
            await callback.answer(f"✅ Срок возврата продлен на {days} дней!", show_alert=True)
            
            # Обновляем список книг
            await show_my_books(callback.message)
            
    except Exception as e:
        logging.error(f"Error in process_extend_days: {e}")
        await callback.answer("Произошла ошибка при продлении срока", show_alert=True)

@router.callback_query(F.data == "cancel_extend")
async def cancel_extend(callback: types.CallbackQuery):
    await show_my_books(callback.message)
    await callback.answer("Продление отменено")

@router.callback_query(F.data.startswith("cancel_booking:"))
async def cancel_booking(callback: types.CallbackQuery):
    try:
        borrow_id = callback.data.split(":")[1]
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем бронь
            cursor.execute("""
                SELECT b.title, bc.id
                FROM borrowed_books bb
                JOIN book_copies bc ON bb.copy_id = bc.id
                JOIN books b ON bc.book_id = b.id
                WHERE bb.id = ? AND bb.status = 'booked'
            """, (borrow_id,))
            
            result = cursor.fetchone()
            if not result:
                await callback.answer("Бронь не найдена или уже отменена", show_alert=True)
                return
                
            title, copy_id = result
            
            # Отменяем бронь
            cursor.execute("""
                UPDATE borrowed_books 
                SET status = 'cancelled' 
                WHERE id = ? AND status = 'booked'
            """, (borrow_id,))
            
            cursor.execute("""
                UPDATE book_copies 
                SET status = 'available' 
                WHERE id = ?
            """, (copy_id,))
            
            conn.commit()
            
            await callback.answer(f"✅ Бронь книги '{title}' отменена", show_alert=True)
            
            # Обновляем список книг
            await show_my_books(callback.message)
            
    except Exception as e:
        logging.error(f"Error in cancel_booking: {e}")
        await callback.answer("Произошла ошибка при отмене брони", show_alert=True)

@router.message(F.text == "📚 Мои книги")
async def show_my_books(message: types.Message):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT 
                    b.title,
                    b.author,
                    bb.status,
                    COALESCE(datetime(bb.return_date), '2000-01-01 00:00:00') as return_date,
                    COALESCE(datetime(bb.borrow_date), '2000-01-01 00:00:00') as borrow_date,
                    bc.id as copy_id,
                    bb.id as borrow_id
                FROM borrowed_books bb
                JOIN book_copies bc ON bb.copy_id = bc.id
                JOIN books b ON bc.book_id = b.id
                WHERE bb.user_id = ? AND bb.status IN ('borrowed', 'booked')
                ORDER BY bb.return_date
            """, (message.from_user.id,))
            
            books = cursor.fetchall()
            
            if not books:
                await message.answer("У вас пока нет книг на руках или забронированных книг")
                return
                
            text = "📚 Ваши книги:\n\n"
            kb = InlineKeyboardBuilder()
            
            borrowed = []
            booked = []
            
            for book in books:
                title, author, status, return_date, borrow_date, copy_id, borrow_id = book
                # Форматируем даты для отображения
                formatted_return = datetime.strptime(return_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                formatted_borrow = datetime.strptime(borrow_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                
                if status == 'borrowed':
                    book_info = (
                        f"📖 {title}\n"
                        f"✍️ {author}\n"
                        f"🔢 ID экземпляра: {copy_id}\n"
                        f"📅 Взята: {formatted_borrow}\n"
                        f"📅 Вернуть до: {formatted_return}\n"
                    )
                    borrowed.append(book_info)
                    kb.button(
                        text=f"🕒 Продлить: {title}",
                        callback_data=f"extend:{borrow_id}"
                    )
                else:
                    book_info = (
                        f"📖 {title}\n"
                        f"✍️ {author}\n"
                        f"🔢 ID экземпляра: {copy_id}\n"
                        f"📅 Дата брони: {formatted_borrow}\n"
                    )
                    booked.append(book_info)
                    kb.button(
                        text=f"❌ Отменить бронь: {title}",
                        callback_data=f"cancel_booking:{borrow_id}"
                    )
            
            if borrowed:
                text += "На руках:\n" + "\n".join(borrowed) + "\n"
            if booked:
                text += "\nЗабронированные:\n" + "\n".join(booked)
            
            kb.adjust(1)
            await message.answer(text, reply_markup=kb.as_markup())
            
    except Exception as e:
        logging.error(f"Error in show_my_books: {e}")
        await message.answer("Произошла ошибка при получении списка книг")

@router.callback_query(F.data.startswith("show_qr_"))
async def show_book_qr(callback: types.CallbackQuery):
    book_id, copy_id = map(int, callback.data.split("_")[2:])
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT b.title, b.author, bc.id
            FROM books b
            JOIN book_copies bc ON b.id = bc.book_id
            WHERE b.id = ? AND bc.id = ?
        """, (book_id, copy_id))
        book = cursor.fetchone()
        
        if not book:
            await callback.answer("Книга не найдена")
            return
        
        qr_data = generate_book_qr(book_id, copy_id)
        
        await callback.message.answer_photo(
            qr_data,
            caption=f"📚 {book[0]}\n✍️ {book[1]}\nID экземпляра: {book[2]}"
        )

@router.callback_query(F.data.startswith("extend_"))
async def extend_book(callback: types.CallbackQuery):
    borrow_id = int(callback.data.split("_")[1])
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT return_date, is_extended
            FROM borrowed_books
            WHERE id = ?
        """, (borrow_id,))
        book = cursor.fetchone()
        
        if not book:
            await callback.answer("Книга не найдена")
            return
        
        if book[1]:
            await callback.answer("Книга уже была продлена один раз", show_alert=True)
            return
        
        # Продлеваем на 14 дней
        new_return_date = (datetime.strptime(book[0], "%Y-%m-%d") + timedelta(days=14)).strftime("%Y-%m-%d")
        
        cursor.execute("""
            UPDATE borrowed_books
            SET return_date = ?, is_extended = 1
            WHERE id = ?
        """, (new_return_date, borrow_id))
        
        conn.commit()
        conn.close()
        
        await callback.answer("Срок возврата продлен на 14 дней!", show_alert=True)
        await show_my_books(callback.message)

# Поиск книг
@router.message(F.text == "🔍 Поиск")
async def search_start(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 По названию", callback_data="search_by_title")
    kb.button(text="✍️ По автору", callback_data="search_by_author")
    kb.button(text="📚 По тематике", callback_data="search_by_theme")
    kb.adjust(1)
    
    await message.answer(
        "Выберите тип поиска:",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data.startswith("search_by_"))
async def search_type_selected(callback: types.CallbackQuery, state: FSMContext):
    search_type = callback.data.split("_")[2]
    await state.update_data(search_type=search_type)
    
    prompts = {
        "title": "Введите название книги:",
        "author": "Введите имя автора:",
        "theme": "Введите тематику (например: роман, фантастика, учебник):"
    }
    
    await callback.message.edit_text(prompts[search_type])
    await state.set_state(UserStates.waiting_for_search)

@router.message(UserStates.waiting_for_search)
async def process_search(message: types.Message, page: int = 1, search_query: str = None):
    menu_commands = ['📚 Каталог', '🔍 Поиск', '📖 Мои книги', '❓ Помощь','📝 Отзывы','📖 Предложить книгу']
    
    if message.text in menu_commands:
        await state.clear()
        return
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        try:
            search_text = search_query if search_query else message.text
            search_pattern = f'%{search_text}%'
            
            cursor.execute("""
                SELECT COUNT(*)
                FROM books
                WHERE LOWER(title) LIKE ? OR LOWER(author) LIKE ?
            """, (search_pattern, search_pattern))
            
            total_books = cursor.fetchone()[0]
            total_pages = (total_books + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE
            
            cursor.execute("""
                SELECT id, title, author, description
                FROM books
                WHERE LOWER(title) LIKE ? OR LOWER(author) LIKE ?
                ORDER BY title
                LIMIT ? OFFSET ?
            """, (search_pattern, search_pattern, BOOKS_PER_PAGE, (page - 1) * BOOKS_PER_PAGE))
            
            books = cursor.fetchall()
            
            if not books:
                await message.answer("Книги не найдены")
                return
            
            text = f"🔍 Результаты поиска '{search_text}' (страница {page} из {total_pages})"
            kb = InlineKeyboardBuilder()
            
            for book_id, title, author, description in books:
                kb.button(
                    text=f"{title} - {author}", 
                    callback_data=f"book_info:{book_id}:{search_text}"
                )
            
            nav_buttons = []
            if page > 1:
                nav_buttons.append(("⬅️ Назад", f"search:{page-1}:{search_text}"))
            if page < total_pages:
                nav_buttons.append(("➡️ Вперед", f"search:{page+1}:{search_text}"))
            
            for btn_text, btn_data in nav_buttons:
                kb.button(text=btn_text, callback_data=btn_data)
            
            kb.adjust(1)
            
            if isinstance(message, types.Message):
                await message.answer(text, reply_markup=kb.as_markup())
            else:
                await message.edit_text(text, reply_markup=kb.as_markup())
            
        except Exception as e:
            logging.error(f"Error in process_search: {e}")
            await message.answer("Произошла ошибка при поиске книг")

@router.callback_query(lambda c: c.data.startswith("search:"))
async def process_search_navigation(callback: types.CallbackQuery):
    try:
        parts = callback.data.split(":")
        page = int(parts[1])
        search_query = parts[2] if len(parts) > 2 else None
        
        await process_search(callback.message, page, search_query)
        await callback.answer()
        
    except Exception as e:
        logging.error(f"Error in search navigation: {e}")
        await callback.message.answer("Произошла ошибка при навигации")

@router.message(F.text == "📝 Отзывы")
async def reviews_menu(message: types.Message):
    try:
        kb = InlineKeyboardBuilder()
        # kb.button(text="📖 Читать отзывы", callback_data="show_all_reviews")
        kb.button(text="✍️ Написать отзыв", callback_data="read_reviews")
        kb.adjust(1)
        
        await message.answer(
            "📝 Меню отзывов:\n\n"
            "• Делитесь своими впечатлениями о прочитанных книгах",
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        logging.error(f"Error in reviews_menu: {e}")
        await message.answer("Произошла ошибка при открытии меню отзывов")

@router.callback_query(F.data == "show_all_reviews")
async def show_all_reviews(callback: types.CallbackQuery):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT b.title, b.author, br.rating, br.review_text, u.full_name, 
                       strftime('%d.%m.%Y', br.created_at) as review_date
                FROM book_reviews br
                JOIN books b ON br.book_id = b.id
                JOIN users u ON br.user_id = u.id
                WHERE br.status = 'approved' AND br.is_hidden = 0
                ORDER BY br.created_at DESC
                LIMIT 10
            """)
            
            reviews = cursor.fetchall()
            
            if not reviews:
                text = "😔 Пока нет отзывов"
            else:
                text = "📚 Последние отзывы:\n\n"
                for title, author, rating, review, reviewer, date in reviews:
                    text += (
                        f"📖 {title} ({author})\n"
                        f"⭐ Оценка: {'⭐' * rating}\n"
                        f"👤 {reviewer}\n"
                        f"✍️ {review}\n"
                        f"📅 {date}\n\n"
                    )
            
            kb = InlineKeyboardBuilder()
            kb.button(text="✍️ Написать отзыв", callback_data="read_reviews")
            kb.button(text="◀️ Назад", callback_data="back_to_reviews")
            kb.adjust(1)
            
            await callback.message.edit_text(text, reply_markup=kb.as_markup())
            
    except Exception as e:
        logging.error(f"Error showing all reviews: {e}")
        await callback.answer("Произошла ошибка при загрузке отзывов", show_alert=True)

@router.callback_query(F.data == "back_to_reviews")
async def back_to_reviews_menu(callback: types.CallbackQuery):
    try:
        kb = InlineKeyboardBuilder()
        # kb.button(text="📖 Читать отзывы", callback_data="show_all_reviews")
        kb.button(text="✍️ Написать отзыв", callback_data="read_reviews")
        kb.adjust(1)
        
        await callback.message.edit_text(
            "📝 Меню отзывов:\n\n"
            # "• Читайте отзывы других читателей\n"
            "• Делитесь своими впечатлениями о прочитанных книгах",
            reply_markup=kb.as_markup()
        )
    except Exception as e:
        logging.error(f"Error in back_to_reviews_menu: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("write_review:"))
async def start_review(callback: types.CallbackQuery, state: FSMContext):
    try:
        book_id = int(callback.data.split(":")[1])
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем, брал ли пользователь эту книгу
            cursor.execute("""
                SELECT COUNT(*) FROM borrowed_books 
                WHERE user_id = ? AND book_id = ? AND status = 'returned'
            """, (callback.from_user.id, book_id))
            
            if cursor.fetchone()[0] == 0:
                await callback.answer("Вы можете оставить отзыв только после прочтения книги", show_alert=True)
                return
            
            # Проверяем, не оставлял ли уже отзыв
            cursor.execute("""
                SELECT COUNT(*) FROM book_reviews 
                WHERE user_id = ? AND book_id = ?
            """, (callback.from_user.id, book_id))
            
            if cursor.fetchone()[0] > 0:
                await callback.answer("Вы уже оставляли отзыв на эту книгу", show_alert=True)
                return
            
            # Получаем название книги
            cursor.execute("SELECT title FROM books WHERE id = ?", (book_id,))
            book_title = cursor.fetchone()[0]
            
            # Сохраняем данные в состояние
            await state.set_state(ReviewStates.waiting_for_rating)
            await state.update_data(book_id=book_id, book_title=book_title)
            
            # Создаем клавиатуру для оценки
            kb = InlineKeyboardBuilder()
            for i in range(1, 6):
                kb.button(text="⭐" * i, callback_data=f"rating:{i}")
            kb.button(text="Отмена", callback_data="cancel_review")
            kb.adjust(5, 1)
            
            await callback.message.edit_text(
                f"📚 Книга: {book_title}\n\n"
                "Оцените книгу от 1 до 5 звёзд:",
                reply_markup=kb.as_markup()
            )
            
    except Exception as e:
        logging.error(f"Error in start_review: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("rating:"))
async def handle_rating(callback: types.CallbackQuery, state: FSMContext):
    try:
        rating = int(callback.data.split(":")[1])
        data = await state.get_data()
        
        await state.update_data(rating=rating)
        await state.set_state(ReviewStates.waiting_for_text)
        
        await callback.message.edit_text(
            f"📚 Книга: {data['book_title']}\n"
            f"⭐ Ваша оценка: {'⭐' * rating}\n\n"
            "✍️ Напишите ваш отзыв. Расскажите:\n"
            "• Общее впечатление\n"
            "• Что понравилось/не понравилось\n"
            "• Кому бы вы рекомендовали эту книгу"
        )
        
    except Exception as e:
        logging.error(f"Error in handle_rating: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.message(ReviewStates.waiting_for_text)
async def save_review(message: types.Message, state: FSMContext):
    try:
        if len(message.text) < 10:
            await message.answer("❌ Отзыв слишком короткий. Напишите, пожалуйста, подробнее.")
            return
            
        data = await state.get_data()
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO book_reviews (
                    book_id, user_id, rating, review_text, created_at, status
                ) VALUES (?, ?, ?, ?, datetime('now'), 'pending')
            """, (
                data['book_id'],
                message.from_user.id,
                data['rating'],
                message.text
            ))
            
            conn.commit()
        
        await state.clear()
        await message.answer(
            f"✅ Спасибо за ваш отзыв о книге «{data['book_title']}»!\n"
            "Он будет опубликован после проверки администратором."
        )
        
    except Exception as e:
        logging.error(f"Error saving review: {e}")
        await message.answer("Произошла ошибка при сохранении отзыва")

@router.callback_query(F.data == "cancel_review")
async def cancel_review(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Написание отзыва отменено")

@router.callback_query(F.data == "read_reviews")
async def show_books_for_reviews(callback: types.CallbackQuery):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем книги, которые пользователь уже вернул
            cursor.execute("""
                SELECT DISTINCT b.id, b.title, b.author
                FROM books b
                JOIN borrowed_books bb ON b.id = bb.book_id
                WHERE bb.user_id = ? AND bb.status = 'returned'
                ORDER BY b.title
            """, (callback.from_user.id,))
            
            returned_books = cursor.fetchall()
            
            if not returned_books:
                await callback.answer("Вы еще не прочитали ни одной книги", show_alert=True)
                return
            
            # Создаем клавиатуру с прочитанными книгами
            kb = InlineKeyboardBuilder()
            
            for book_id, title, author in returned_books:
                # Проверяем, не оставлял ли уже отзыв
                cursor.execute("""
                    SELECT COUNT(*) FROM book_reviews 
                    WHERE user_id = ? AND book_id = ?
                """, (callback.from_user.id, book_id))
                
                has_review = cursor.fetchone()[0] > 0
                
                if not has_review:
                    kb.button(
                        text=f"📚 {title} ({author})",
                        callback_data=f"write_review:{book_id}"
                    )
            
            kb.button(text="◀️ Главное меню", callback_data="start")
            kb.adjust(1)
            
            text = (
                "📖 Выберите книгу, чтобы написать отзыв:\n\n"
                "Показаны только книги, которые вы уже прочитали и еще не оставили отзыв."
            )
            
            if callback.message.text != text:
                await callback.message.edit_text(text, reply_markup=kb.as_markup())
            else:
                await callback.message.edit_reply_markup(reply_markup=kb.as_markup())
                
    except Exception as e:
        logging.error(f"Error in show_books_for_reviews: {e}")
        await callback.answer("Произошла ошибка при загрузке списка книг", show_alert=True)

@router.message(F.text == "❓ Инструкция")
async def show_instructions(message: types.Message):
    instructions = """
📚 <b>Инструкция по использованию библиотечного бота:</b>

1️⃣ <b>Поиск и бронирование книг:</b>
• Используйте кнопку 📚 Каталог для просмотра всех книг
• Кнопка 🔍 Поиск поможет найти конкретную книгу
• Нажмите на книгу для просмотра подробной информации
• Используйте кнопку "Взять книгу" для бронирования

2️⃣ <b>Управление взятыми книгами:</b>
• В разделе 📖 Мои книги показаны ваши книги
• Можно продлить срок возврата

3️⃣ <b>Отзывы:</b>
• Читайте отзывы других пользователей
• Оставляйте свои отзывы и оценки

⚠️ <b>Важные правила:</b>
• Максимум 3 книги на руках
• Срок возврата - 14 дней
• Можно продлить срок один раз
• Не забывайте возвращать книги вовремя!

Приятного чтения! 📚
"""
    await message.answer(instructions, parse_mode="HTML")

@router.message(F.text == "Забронировать")
async def show_booking_options(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="🔍 Поиск по названию", callback_data="search_by_title")
    kb.button(text="👤 Поиск по автору", callback_data="search_by_author")
    kb.button(text="📚 Поиск по тематике", callback_data="search_by_theme")
    kb.adjust(1)
    
    await message.answer(
        "Выберите способ поиска книги:",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data.startswith("search_by_"))
async def start_search(callback: types.CallbackQuery, state: FSMContext):
    search_type = callback.data.split("_")[2]
    await state.update_data(search_type=search_type)
    
    prompts = {
        "title": "Введите название книги:",
        "author": "Введите имя автора:",
        "theme": "Введите тематику (например: роман, фантастика, учебник):"
    }
    
    await callback.message.edit_text(prompts[search_type])
    await state.set_state(UserStates.waiting_for_search)

@router.message(UserStates.waiting_for_search)
async def process_search(message: types.Message, page: int = 1, search_query: str = None):
    menu_commands = ['📚 Каталог', '🔍 Поиск', '📖 Мои книги', '❓ Помощь']
    
    if message.text in menu_commands:
        await state.clear() 
        return  
    
    # Иначе продолжаем поиск
    with get_db() as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT COUNT(*)
                FROM books
                WHERE LOWER(title) LIKE ? OR LOWER(author) LIKE ?
            """, (f'%{message.text}%', f'%{message.text}%'))
            
            total_books = cursor.fetchone()[0]
            total_pages = (total_books + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE
            
            cursor.execute("""
                SELECT id, title
                FROM books
                WHERE LOWER(title) LIKE ? OR LOWER(author) LIKE ?
                ORDER BY title
                LIMIT ? OFFSET ?
            """, (f'%{message.text}%', f'%{message.text}%', BOOKS_PER_PAGE, (page - 1) * BOOKS_PER_PAGE))
            
            books = cursor.fetchall()
            
            if not books:
                await message.answer(
                    "🔍 По вашему запросу ничего не найдено.\n"
                    "Попробуйте изменить запрос или вернуться в меню.",
                    reply_markup=get_main_keyboard()
                )
                return
            
            text = f"🔍 Результаты поиска '{message.text}' (страница {page} из {total_pages})"
            kb = InlineKeyboardBuilder()
            
            for book_id, title in books:
                kb.button(
                    text=title, 
                    callback_data=f"book_info:{book_id}:{message.text}"  
                )
            
            if total_pages > 1:
                nav_buttons = []
                if page > 1:
                    nav_buttons.append(("⬅️ Назад", f"search:{page-1}:{message.text}"))
                if page < total_pages:
                    nav_buttons.append(("➡️ Вперед", f"search:{page+1}:{message.text}"))
                
                for btn_text, btn_data in nav_buttons:
                    kb.button(text=btn_text, callback_data=btn_data)
            
            kb.button(text="◀️ В меню", callback_data="back_to_menu")
            
            kb.adjust(1)
            await message.answer(text, reply_markup=kb.as_markup())
            
        except Exception as e:
            logging.error(f"Error in process_search: {e}")
            await message.answer(
                "Произошла ошибка при поиске книг. Попробуйте позже.",
                reply_markup=get_main_keyboard()
            )

@router.callback_query(F.data.startswith("back_to_search:"))
async def back_to_search_results(callback: types.CallbackQuery):
    try:
        search_query = callback.data.split(":")[1]
        await callback.message.delete()
        await process_search(callback.message, page=1, search_query=search_query)
    except Exception as e:
        logging.error(f"Error in back_to_search_results: {e}")
        await callback.answer("Произошла ошибка при возврате к результатам поиска", show_alert=True)

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "Выберите действие:",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "Запрос на книгу")
async def start_book_request(message: types.Message):
    await message.answer(
        "Пожалуйста, отправьте информацию о книге в формате:\n"
        "Название: [название книги]\n"
        "Автор: [автор]\n"
        "Причина: [почему вы считаете, что эта книга нужна библиотеке]"
    )
    await UserStates.waiting_for_book_request.set()

@router.message(UserStates.waiting_for_book_request)
async def process_book_request(message: types.Message, state: FSMContext):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO book_requests (user_id, request_text, status, date)
            VALUES (?, ?, 'pending', ?)
        """, (
            message.from_user.id,
            message.text,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
        
        await message.answer(
            "Спасибо за запрос! Администрация рассмотрит ваше предложение."
        )
        await state.clear()

@router.message(F.text == "📖 Предложить книгу")
async def suggest_book_start(message: types.Message, state: FSMContext):
    logging.debug(f"Suggest book handler triggered with message: {message.text}")
    
    if not await check_registration(message):
        logging.debug("User not registered")
        return
        
    try:
        logging.debug("Setting state and sending message")
        await state.set_state(SuggestBookStates.waiting_for_title)
        await message.answer(
            "📚 Предложите книгу для библиотеки!\n\n"
            "Пожалуйста, отправьте название книги и автора в формате:\n"
            "Название - Автор\n\n"
            "Например: Война и мир - Лев Толстой"
        )
        logging.debug("Message sent successfully")
        
    except Exception as e:
        logging.error(f"Error in suggest_book_start: {e}", exc_info=True)
        await message.answer("❌ Произошла ошибка. Попробуйте позже.")

@router.message(SuggestBookStates.waiting_for_title)
async def process_book_title(message: types.Message, state: FSMContext):
    await state.update_data(title=message.text)
    await message.answer(
        "Отправьте ссылку, где можно купить эту книгу:\n"
        "Например: https://example.com/book"
    )
    await state.set_state(SuggestBookStates.waiting_for_url)

@router.message(SuggestBookStates.waiting_for_url)
async def process_book_url(message: types.Message, state: FSMContext):
    if not message.text.startswith(('http://', 'https://')):
        await message.answer(
            "❌ Пожалуйста, отправьте корректную ссылку, начинающуюся с http:// или https://"
        )
        return
        
    await state.update_data(url=message.text)
    await message.answer(
        "Укажите стоимость книги (в рублях):\n"
        "Например: 1500"
    )
    await state.set_state(SuggestBookStates.waiting_for_price)

@router.message(SuggestBookStates.waiting_for_price)
async def process_book_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text)
        if price <= 0:
            raise ValueError
            
        await state.update_data(price=price)
        await message.answer(
            "Опишите, почему эту книгу стоит добавить в библиотеку:\n"
            "Например: Это популярная книга по программированию, которая поможет многим читателям"
        )
        await state.set_state(SuggestBookStates.waiting_for_reason)
        
    except ValueError:
        await message.answer("❌ Пожалуйста, введите корректную цену (целое положительное число)")

@router.message(SuggestBookStates.waiting_for_reason)
async def process_book_reason(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO book_suggestions (
                    user_id, title, url, price, reason, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', datetime('now'))
            """, (
                message.from_user.id,
                data['title'],
                data['url'],
                data['price'],
                message.text
            ))
            
            conn.commit()
            
            await message.answer(
                "✅ Спасибо за предложение!\n\n"
                "Администраторы рассмотрят вашу заявку.\n"
                "Мы учтем ваше пожелание при пополнении библиотеки."
            )
            
        except Exception as e:
            logging.error(f"Error in process_book_reason: {e}")
            await message.answer("❌ Произошла ошибка при сохранении предложения. Попробуйте позже.")
        finally:
            conn.close()
            await state.clear() 