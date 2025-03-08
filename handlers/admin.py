import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import get_db, create_book_copies, log_admin_action
from states.admin_states import AdminStates, AdminManageStates, AdminTeacherStates
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import secrets
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardRemove
from utils.token_storage import add_token, remove_token
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import io
from PIL import Image
import logging
from functools import wraps
from typing import Callable, Any

router = Router()

ADMIN_IDS = [6500936622] 

# Функция проверки админа
async def check_admin(message: types.Message) -> bool:
    try:
        with get_db() as conn:  # Используем контекстный менеджер правильно
            cursor = conn.cursor()
            cursor.execute("SELECT role FROM users WHERE id = ?", (message.from_user.id,))
            result = cursor.fetchone()
            return result and result[0] == 'admin'
    except Exception as e:
        logging.error(f"Error checking admin status: {e}")
        return False

# Добавляем фильтр для админских команд
async def admin_filter(message: types.Message):
    return await check_admin(message)

# Удаляем глобальный фильтр
# router.message.filter(admin_filter)

def get_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔍 Сканировать QR"),
                KeyboardButton(text="📊 Статистика")
            ],
            [
                KeyboardButton(text="🌐 Веб-панель"),
                KeyboardButton(text="👥 Управление админами")
            ],
            [
                KeyboardButton(text="👥 Управление учителями"),
                KeyboardButton(text="◀️ Выйти из панели админа")
            ]
        ],
        resize_keyboard=True
    )
    return keyboard

def admin_required(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(message: types.Message, *args: Any, **kwargs: Any) -> Any:
        if not await check_admin(message):
            await message.answer("⛔️ У вас нет прав администратора")
            return
        return await func(message, *args, **kwargs)
    return wrapper

# Использование декоратора
@router.message(Command("admin"))
@admin_required
async def admin_panel(message: types.Message):
    await message.answer(
        "🔐 Панель администратора\n\n"
        "Выберите нужное действие:",
        reply_markup=get_admin_keyboard()
    )

@router.message(F.text == "🔍 Сканировать QR")
async def scan_qr_command(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Выдать одну книгу", callback_data="scan_issue_new")
    kb.button(text="📥 Вернуть одну книгу", callback_data="scan_return")
    kb.button(text="📚 Выдача учебников", callback_data="mass_issue")
    kb.button(text="📚 Возврат учебников", callback_data="mass_return")
    kb.adjust(2)
    
    await message.answer(
        "📷 Выберите действие для сканирования:",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "scan_issue_new")
async def start_issue_book(callback: types.CallbackQuery, state: FSMContext):
    try:
        logging.warning(f"DEBUG: Обработчик scan_issue_new сработал")
        # Сначала очищаем состояние, чтобы избежать конфликтов
        await state.clear()
        
        # Устанавливаем состояние ожидания QR-кода ученика
        await state.set_state(AdminStates.waiting_for_student_qr)
        
        # Отправляем сообщение с инструкцией
        await callback.message.answer(
            "1️⃣ Отсканируйте QR-код ученика или отправьте его ID:",
            reply_markup=ReplyKeyboardRemove()
        )
        
        # Подтверждаем нажатие кнопки
        await callback.answer("Ожидание QR-кода ученика")
        
        # Логируем для отладки
        logging.info(f"Set state to waiting_for_student_qr for user {callback.from_user.id}")
    except Exception as e:
        logging.error(f"Error in start_issue_book: {e}")
        await callback.answer("Произошла ошибка", show_alert=True)

@router.message(F.text == "🌐 Веб-панель", admin_filter)
async def web_panel(message: types.Message):
    token = secrets.token_urlsafe(32)
    expires = datetime.now() + timedelta(hours=24)  # Токен на 24 часа
    
    add_token(token, message.from_user.id, expires)
    
    panel_url = f"http://localhost:8000/login?token={token}"
    
    await message.answer(
        "🌐 Доступ к веб-панели:\n\n"
        f"🔗 {panel_url}\n\n"
        "⚠️ Важно:\n"
        "• Ссылка действительна 24 часа\n"
        "• Не передавайте её третьим лицам\n"
        "• После истечения срока нужно будет сгенерировать новую\n\n"
        "🔒 В целях безопасности рекомендуется использовать ссылку только с доверенных устройств.",
        disable_web_page_preview=True
    )

@router.message(F.text == "👥 Управление админами")
async def manage_admins(message: types.Message):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем, является ли пользователь супер-админом (ID: 6500936622)
            if message.from_user.id != 6500936622:
                await message.answer("❌ У вас нет прав для управления админами")
                return
            
            # Получаем список всех админов
            cursor.execute("""
                SELECT id, username, full_name 
                FROM users 
                WHERE role = 'admin'
                ORDER BY id
            """)
            admins = cursor.fetchall()
            
            # Формируем сообщение со списком админов
            text = "👥 Список администраторов:\n\n"
            for admin_id, username, full_name in admins:
                text += f"• {full_name or username or admin_id} (ID: {admin_id})\n"
            
            # Создаем клавиатуру
            kb = InlineKeyboardBuilder()
            kb.button(text="➕ Добавить админа", callback_data="add_admin")
            kb.button(text="➖ Удалить админа", callback_data="remove_admin")
            kb.adjust(1)
            
            await message.answer(text, reply_markup=kb.as_markup())
            
    except Exception as e:
        logging.error(f"Error in manage_admins: {e}")
        await message.answer("❌ Произошла ошибка при получении списка админов")

@router.message(F.text == "📊 Статистика")
async def show_stats(message: types.Message):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем общую статистику
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) as admin_count,
                    SUM(CASE WHEN role = 'user' THEN 1 ELSE 0 END) as user_count
                FROM users
            """)
            total_users, admin_count, user_count = cursor.fetchone()
            
            # Получаем статистику по книгам
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT b.id) as total_books,
                    COUNT(DISTINCT bc.id) as total_copies,
                    COUNT(DISTINCT CASE WHEN bb.status = 'borrowed' THEN bb.id END) as borrowed_books,
                    COUNT(DISTINCT CASE WHEN bb.status = 'booked' THEN bb.id END) as booked_books,
                    COUNT(DISTINCT br.id) as total_reviews
                FROM books b
                LEFT JOIN book_copies bc ON b.id = bc.book_id
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id
                LEFT JOIN book_reviews br ON b.id = br.book_id
            """)
            total_books, total_copies, borrowed_books, booked_books, total_reviews = cursor.fetchone()
            
            # Формируем сообщение
            stats_message = (
                "📊 Статистика библиотеки:\n\n"
                f"👥 Пользователи:\n"
                f"• Всего: {total_users}\n"
                f"• Администраторов: {admin_count}\n"
                f"• Пользователей: {user_count}\n\n"
                f"📚 Книги:\n"
                f"• Всего книг: {total_books}\n"
                f"• Всего экземпляров: {total_copies}\n"
                f"• Выдано: {borrowed_books}\n"
                f"• Забронировано: {booked_books}\n"
                f"• Отзывов: {total_reviews}"
            )
            
            await message.answer(stats_message)
            
    except Exception as e:
        logging.error(f"Error showing stats: {e}")
        await message.answer("❌ Произошла ошибка при получении статистики")

@router.message(F.text == "◀️ Выйти из панели админа")
async def return_to_user_menu(message: types.Message):
    from handlers.user import get_main_keyboard
    
    await message.answer(
        "Вы вернулись в обычное меню",
        reply_markup=get_main_keyboard()
    )

@router.callback_query(F.data == "scan_qr")
async def scan_qr_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Выдать книгу", callback_data="scan_issue")
    kb.button(text="📥 Вернуть книгу", callback_data="scan_return")
    # kb.button(text="◀️ Назад", callback_data="admin")
    kb.adjust(2, 1)
    
    await callback.message.edit_text(
        "📷 Выберите действие для сканирования QR-кода:",
        reply_markup=kb.as_markup()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("scan_"))
async def handle_scan_action(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data.split("_")[1]
    
    if action == "issue":
        await state.set_state(AdminStates.waiting_for_qr)
        await callback.message.answer(
            "📷 Отсканируйте QR-код книги, которую хотите выдать"
        )
    elif action == "return":
        await state.set_state(AdminStates.waiting_for_return_qr)
        await callback.message.answer(
            "📷 Отсканируйте QR-код книги, которую хотите вернуть"
        )
    
    await callback.answer()

@router.message(AdminStates.waiting_for_qr, F.photo)
async def process_qr_photo(message: types.Message, state: FSMContext):
    try:
        # Скачиваем фото
        photo = await message.bot.get_file(message.photo[-1].file_id)
        photo_bytes = await message.bot.download_file(photo.file_path)
        
        # Конвертируем в формат для opencv
        nparr = np.frombuffer(photo_bytes.read(), np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Декодируем QR-код
        decoded_objects = decode(image)
        
        if not decoded_objects:
            await message.answer(
                "❌ QR-код не найден.\n\n"
                "Убедитесь, что:\n"
                "• QR-код хорошо освещен\n"
                "• Изображение не размыто\n"
                "• QR-код полностью попадает в кадр"
            )
            return
            
        # Получаем ID экземпляра из QR-кода
        copy_id = decoded_objects[0].data.decode('utf-8')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем статус экземпляра и получаем информацию о книге
            cursor.execute("""
                SELECT 
                    bc.status,
                    b.id as book_id,
                    b.title,
                    b.author,
                    COALESCE(bb.status, 'none') as borrow_status
                FROM book_copies bc
                JOIN books b ON bc.book_id = b.id
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id 
                    AND bb.status = 'borrowed'
                WHERE bc.id = ?
            """, (copy_id,))
            
            copy_info = cursor.fetchone()
            if not copy_info:
                await message.answer("❌ Книга не найдена в базе данных")
                return
                
            status, book_id, title, author, borrow_status = copy_info
            
            # Проверяем, не выдана ли уже книга
            if borrow_status == 'borrowed':
                await message.answer(
                    "❌ Этот экземпляр уже выдан читателю\n"
                    f"Текущий статус: {status}"
                )
                return
            
            # Теперь получаем информацию о бронированиях
            cursor.execute("""
                SELECT 
                    r.id as reservation_id,
                    r.user_id,
                    u.full_name,
                    u.username,
                    r.created_at
                FROM book_reservations r
                JOIN users u ON r.user_id = u.id
                WHERE r.book_id = ? 
                AND r.status = 'pending'
                ORDER BY r.created_at ASC
            """, (book_id,))
            
            reservations = cursor.fetchall()
            
            if not reservations:
                await message.answer(
                    f"❌ Нет активных бронирований на книгу:\n"
                    f"📖 {title}\n"
                    f"✍️ {author}"
                )
                return
            
            # Создаем клавиатуру с списком ожидающих
            kb = InlineKeyboardBuilder()
            
            for res_id, user_id, full_name, username, created_at in reservations:
                display_name = full_name or f"@{username}"
                created_at_fmt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%d.%m %H:%M")
                kb.button(
                    text=f"{display_name} (забронировано: {created_at_fmt})",
                    callback_data=f"issue_{copy_id}_{res_id}"
                )
            
            kb.adjust(1)
            
            await state.update_data(book_title=title)
            await message.answer(
                f"📚 Выберите читателя для выдачи книги:\n"
                f"«{title}» - {author}",
                reply_markup=kb.as_markup()
            )
            
    except Exception as e:
        logging.error(f"Error processing QR: {e}")
        await message.answer("❌ Произошла ошибка при обработке QR-кода")
        await state.clear()

@router.callback_query(F.data.startswith("issue_"))
async def issue_book(callback: types.CallbackQuery, state: FSMContext):
    try:
        _, copy_id, reservation_id = callback.data.split("_")
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем информацию о бронировании
            cursor.execute("""
                SELECT 
                    r.user_id,
                    r.book_id,
                    u.full_name,
                    u.username,
                    b.title
                FROM book_reservations r
                JOIN users u ON r.user_id = u.id
                JOIN books b ON r.book_id = b.id
                WHERE r.id = ?
            """, (reservation_id,))
            
            user_id, book_id, full_name, username, book_title = cursor.fetchone()
            display_name = full_name or f"@{username}"
            
            # Создаем запись о выдаче книги
            cursor.execute("""
                INSERT INTO borrowed_books (
                    user_id,
                    book_id,
                    copy_id,
                    reservation_id,
                    borrow_date,
                    return_date,
                    status
                ) VALUES (
                    ?, ?, ?, ?, datetime('now'), datetime('now', '+14 days'), 'borrowed'
                )
            """, (user_id, book_id, copy_id, reservation_id))
            
            # Обновляем статус бронирования
            cursor.execute("""
                UPDATE book_reservations 
                SET status = 'fulfilled' 
                WHERE id = ?
            """, (reservation_id,))
            
            # Обновляем статус экземпляра
            cursor.execute("""
                UPDATE book_copies 
                SET status = 'borrowed' 
                WHERE id = ?
            """, (copy_id,))
            
            conn.commit()
            
            # Уведомляем библиотекаря
            await callback.message.edit_text(
                f"✅ Книга выдана:\n"
                f"📖 {book_title}\n"
                f"👤 Читатель: {display_name}"
            )
            
            # Уведомляем пользователя
            await callback.bot.send_message(
                user_id,
                f"📚 Ваша книга «{book_title}» выдана!\n"
                f"📅 Срок возврата: через 14 дней"
            )
            
            await state.clear()
            
    except Exception as e:
        logging.error(f"Error in issue_book: {e}")
        await callback.answer("❌ Произошла ошибка при выдаче книги", show_alert=True)

@router.message(AdminStates.waiting_for_user_id)
async def process_user_id(message: types.Message, state: FSMContext):
    try:
        user_id = int(message.text)
        data = await state.get_data()
        book_id = data.get('book_id')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем книгу и пользователя
            cursor.execute("""
                SELECT b.title, b.author, bc.id as copy_id, bc.status,
                       bb.status as borrow_status, u.full_name, u.username
                FROM books b
                JOIN book_copies bc ON b.id = bc.book_id
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id 
                    AND bb.status = 'borrowed'
                JOIN users u ON u.id = ?
                WHERE bc.id = ?
            """, (user_id, book_id))
            
            book_info = cursor.fetchone()
            if not book_info:
                await message.answer("❌ Книга или пользователь не найдены в базе данных")
                await state.clear()
                return
                
            title, author, copy_id, status, borrow_status, user_full_name, username = book_info
            display_name = user_full_name or f"@{username}"
            
            # Выдаем книгу
            return_date = datetime.now() + timedelta(days=14)
            cursor.execute("""
                UPDATE book_copies 
                SET status = 'borrowed' 
                WHERE id = ?
            """, (copy_id,))
            
            cursor.execute("""
                INSERT INTO borrowed_books (user_id, copy_id, borrow_date, return_date, status)
                VALUES (?, ?, datetime('now'), ?, 'borrowed')
            """, (user_id, copy_id, return_date.strftime("%Y-%m-%d")))
            
            conn.commit()
            
            # Уведомления
            await message.answer(
                f"✅ Книга успешно выдана:\n"
                f"📖 {title}\n"
                f"✍️ {author}\n"
                f"👤 Читатель: {display_name}\n"
                f"📅 Вернуть до: {return_date.strftime('%d.%m.%Y')}"
            )
            
            try:
                await message.bot.send_message(
                    user_id,
                    f"📚 Вам выдана книга:\n"
                    f"📖 {title}\n"
                    f"✍️ {author}\n"
                    f"📅 Срок возврата: {return_date.strftime('%d.%m.%Y')}\n\n"
                    f"Приятного чтения! 😊"
                )
            except Exception as e:
                logging.error(f"Error sending notification to user: {e}")
            
            await state.clear()
            
    except ValueError:
        await message.answer("❌ Введите корректный ID пользователя (число)")
    except Exception as e:
        logging.error(f"Error processing user ID: {e}")
        await message.answer("❌ Произошла ошибка при обработке")
        await state.clear()

@router.callback_query(F.data == "add_admin")
async def add_admin_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminManageStates.waiting_for_new_admin_id)
    await callback.message.edit_text(
        "Отправьте ID пользователя, которого хотите сделать администратором:",
        reply_markup=InlineKeyboardBuilder().button(
            text="◀️ Назад", callback_data="back_to_admin_menu"
        ).as_markup()
    )
    await callback.answer()

@router.callback_query(F.data == "remove_admin")
async def remove_admin_start(callback: types.CallbackQuery, state: FSMContext):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем права доступа
            cursor.execute("SELECT role FROM users WHERE id = ?", (callback.from_user.id,))
            user = cursor.fetchone()
            if not user or user[0] != 'admin':
                await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
                return
            
            # Получаем список админов
            cursor.execute("""
                SELECT id, username, full_name 
                FROM users 
                WHERE role = 'admin' AND id != ?
                ORDER BY full_name, username
            """, (callback.from_user.id,))
            
            admins = cursor.fetchall()
            
            if not admins:
                await callback.answer("Нет других администраторов", show_alert=True)
                return
                
            kb = InlineKeyboardBuilder()
            for admin_id, username, full_name in admins:
                display_name = full_name or username or str(admin_id)
                kb.button(
                    text=f"❌ {display_name}", 
                    callback_data=f"confirm_remove_admin:{admin_id}"
                )
            kb.button(text="◀️ Назад", callback_data="back_to_admin_menu")
            kb.adjust(1)
            
            await callback.message.edit_text(
                "Выберите администратора для удаления:",
                reply_markup=kb.as_markup()
            )
            await callback.answer()
            
    except Exception as e:
        logging.error(f"Error in remove_admin_start: {e}")
        await callback.answer("❌ Произошла ошибка", show_alert=True)

@router.callback_query(F.data.startswith("confirm_remove_admin:"))
async def confirm_remove_admin(callback: types.CallbackQuery):
    try:
        admin_id = int(callback.data.split(":")[1])
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Начинаем транзакцию
            cursor.execute("BEGIN")
            
            try:
                # Проверяем права доступа
                cursor.execute("SELECT role FROM users WHERE id = ?", (callback.from_user.id,))
                user = cursor.fetchone()
                if not user or user[0] != 'admin':
                    await callback.answer("❌ У вас нет прав для этого действия", show_alert=True)
                    return
                
                # Получаем информацию об удаляемом админе
                cursor.execute("""
                    SELECT username, full_name 
                    FROM users 
                    WHERE id = ? AND role = 'admin'
                """, (admin_id,))
                admin = cursor.fetchone()
                
                if not admin:
                    await callback.answer("❌ Администратор не найден", show_alert=True)
                    return
                
                # Снимаем права администратора
                cursor.execute("""
                    UPDATE users 
                    SET role = 'user' 
                    WHERE id = ?
                """, (admin_id,))
                
                # Логируем действие
                cursor.execute("""
                    INSERT INTO admin_logs (admin_id, action_type, details, timestamp)
                    VALUES (?, 'remove_admin', ?, datetime('now'))
                """, (
                    callback.from_user.id,
                    f"Удален администратор {admin[1] or admin[0]} (ID: {admin_id})"
                ))
                
                # Завершаем транзакцию
                conn.commit()
                
                kb = InlineKeyboardBuilder()
                kb.button(text="◀️ Назад", callback_data="back_to_admin_menu")
                
                await callback.message.edit_text(
                    f"✅ Администратор успешно удален",
                    reply_markup=kb.as_markup()
                )
                await callback.answer()
                
            except Exception as e:
                # В случае ошибки откатываем транзакцию
                cursor.execute("ROLLBACK")
                raise e
                
    except Exception as e:
        logging.error(f"Error in confirm_remove_admin: {e}")
        await callback.answer("❌ Произошла ошибка при удалении администратора", show_alert=True)

@router.message(AdminManageStates.waiting_for_new_admin_id)
async def process_new_admin_id(message: types.Message, state: FSMContext):
    try:
        new_admin_id = int(message.text)
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем существование пользователя
            cursor.execute("SELECT id, role FROM users WHERE id = ?", (new_admin_id,))
            user = cursor.fetchone()
            
            if not user:
                await message.answer(
                    "❌ Пользователь не найден. Убедитесь, что он начал диалог с ботом.",
                    reply_markup=InlineKeyboardBuilder().button(
                        text="◀️ Назад", callback_data="back_to_admin_menu"
                    ).as_markup()
                )
                await state.clear()
                return
                
            if user[1] == 'admin':
                await message.answer(
                    "❌ Этот пользователь уже является администратором",
                    reply_markup=InlineKeyboardBuilder().button(
                        text="◀️ Назад", callback_data="back_to_admin_menu"
                    ).as_markup()
                )
                await state.clear()
                return
                
            # Назначаем пользователя админом
            cursor.execute("UPDATE users SET role = 'admin' WHERE id = ?", (new_admin_id,))
            conn.commit()
            
            # Логируем действие
            log_admin_action(
                admin_id=message.from_user.id,
                action_type="add_admin",
                details=f"Добавлен новый администратор (ID: {new_admin_id})"
            )
            
            await message.answer(
                "✅ Новый администратор успешно добавлен",
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Назад", callback_data="back_to_admin_menu"
                ).as_markup()
            )
            await state.clear()
            
    except ValueError:
        await message.answer(
            "❌ Пожалуйста, отправьте числовой ID пользователя",
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Назад", callback_data="back_to_admin_menu"
            ).as_markup()
        )
    except Exception as e:
        logging.error(f"Error adding new admin: {e}")
        await message.answer(
            "❌ Произошла ошибка при добавлении администратора",
            reply_markup=InlineKeyboardBuilder().button(
                text="◀️ Назад", callback_data="back_to_admin_menu"
            ).as_markup()
        )
    finally:
        await state.clear()

@router.callback_query(F.data == "back_to_admin_menu")
async def back_to_admin_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить админа", callback_data="add_admin")
    kb.button(text="➖ Удалить админа", callback_data="remove_admin")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "👨‍💼 Управление администраторами",
        reply_markup=kb.as_markup()
    )
    await callback.answer()

async def get_admin_list() -> list:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, username, full_name 
            FROM users 
            WHERE role = 'admin'
        """)
        return cursor.fetchall()
    finally:
        conn.close()

async def update_user_role(user_id: int, new_role: str) -> bool:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error updating user role: {e}")
        return False
    finally:
        conn.close()

async def get_book_info(copy_id: str) -> tuple:
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 
                b.title,
                bb.user_id,
                u.full_name,
                u.username,
                bb.id as borrow_id
            FROM book_copies bc
            JOIN borrowed_books bb ON bc.id = bb.copy_id
            JOIN books b ON bc.book_id = b.id
            JOIN users u ON bb.user_id = u.id
            WHERE bc.id = ? AND bb.status = 'booked'
        """, (copy_id,))
        return cursor.fetchone()
    finally:
        conn.close()

@router.message(AdminStates.waiting_for_return_qr, F.photo)
async def process_return_qr(message: types.Message, state: FSMContext):
    try:
        # Скачиваем фото
        photo = await message.bot.get_file(message.photo[-1].file_id)
        photo_bytes = await message.bot.download_file(photo.file_path)
        
        # Конвертируем в формат для opencv
        nparr = np.frombuffer(photo_bytes.read(), np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Декодируем QR-код
        decoded_objects = decode(image)
        
        if not decoded_objects:
            await message.answer(
                "❌ QR-код не найден.\n\n"
                "Убедитесь, что:\n"
                "• QR-код хорошо освещен\n"
                "• Изображение не размыто\n"
                "• QR-код полностью попадает в кадр"
            )
            return
            
        # Получаем ID экземпляра из QR-кода
        copy_id = decoded_objects[0].data.decode('utf-8')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем информацию о взятой книге
            cursor.execute("""
                SELECT 
                    bb.id as borrow_id,
                    b.title,
                    u.full_name,
                    u.username,
                    u.id as user_id,
                    bb.borrow_date,
                    bb.return_date,
                    bc.status as copy_status
                FROM book_copies bc
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id AND bb.status = 'borrowed'
                LEFT JOIN books b ON bc.book_id = b.id
                LEFT JOIN users u ON bb.user_id = u.id
                WHERE bc.id = ?
            """, (copy_id,))
            
            book_info = cursor.fetchone()
            
            if not book_info:
                await message.answer("❌ Книга не найдена в базе данных")
                return
                
            borrow_id, title, full_name, username, user_id, borrow_date, return_date, copy_status = book_info
            
            if copy_status != 'borrowed':
                await message.answer(
                    "❌ Эта книга не числится на руках\n"
                    f"Текущий статус: {copy_status}"
                )
                return
            
            if not borrow_id:
                await message.answer("❌ Не найдена информация о выдаче этой книги")
                return
                
            display_name = full_name or f"@{username}"
            
            # Обновляем статусы
            cursor.execute("""
                UPDATE borrowed_books 
                SET status = 'returned' 
                WHERE id = ?
            """, (borrow_id,))
            
            cursor.execute("""
                UPDATE book_copies 
                SET status = 'available' 
                WHERE id = ?
            """, (copy_id,))
            
            conn.commit()
            
            # Уведомляем библиотекаря
            await message.answer(
                f"✅ Книга успешно возвращена:\n"
                f"📖 {title}\n"
                f"👤 Читатель: {display_name}\n"
                f"📅 Была выдана: {datetime.strptime(borrow_date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')}"
            )
            
            # Уведомляем пользователя
            try:
                await message.bot.send_message(
                    user_id,
                    f"📚 Спасибо, что вернули книгу:\n"
                    f"«{title}»\n\n"
                    f"Ждем вас снова! 😊"
                )
            except Exception as e:
                logging.error(f"Error sending return notification to user: {e}")
            
            await state.clear()
            
    except Exception as e:
        logging.error(f"Error in process_return_qr: {e}")
        await message.answer("❌ Произошла ошибка при обработке возврата")
        await state.clear()

@router.message(F.text == "👥 Управление учителями")
@admin_required
async def manage_teachers(message: types.Message):
    if message.from_user.id != 6500936622:  # ID главного админа
        await message.answer("❌ Эта функция доступна только главному администратору")
        return
        
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить учителя", callback_data="add_teacher")
    kb.button(text="➖ Удалить учителя", callback_data="remove_teacher")
    kb.button(text="📋 Список учителей", callback_data="list_teachers")
    kb.adjust(1)
    
    await message.answer(
        "👨‍🏫 Управление учителями\n"
        "Выберите действие:",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "add_teacher")
async def start_add_teacher(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != 6500936622:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
        
    await callback.message.answer(
        "Отправьте ID пользователя Telegram будущего учителя\n"
        "(пользователь должен быть зарегистрирован в боте)"
    )
    await state.set_state(AdminTeacherStates.waiting_for_teacher_id)
    await callback.answer()

@router.message(AdminTeacherStates.waiting_for_teacher_id)
async def process_teacher_id(message: types.Message, state: FSMContext):
    try:
        teacher_id = int(message.text)
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, role FROM users WHERE id = ?
            """, (teacher_id,))
            
            user = cursor.fetchone()
            if not user:
                await message.answer("❌ Пользователь не найден в базе данных")
                return
                
            if user[1] == 'teacher':
                await message.answer("❌ Этот пользователь уже является учителем")
                return
                
            await state.update_data(teacher_id=teacher_id)
            await message.answer("Введите ФИО учителя:")
            await state.set_state(AdminTeacherStates.waiting_for_teacher_name)
            
    except ValueError:
        await message.answer("❌ Введите корректный ID")

@router.message(AdminTeacherStates.waiting_for_teacher_name)
async def process_teacher_name(message: types.Message, state: FSMContext):
    await state.update_data(teacher_name=message.text)
    await message.answer("Введите класс учителя (например: 5А):")
    await state.set_state(AdminTeacherStates.waiting_for_teacher_class)

@router.message(AdminTeacherStates.waiting_for_teacher_class)
async def process_teacher_class(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Обновляем данные пользователя
        cursor.execute("""
            UPDATE users 
            SET role = 'teacher',
                full_name = ?,
                class = ?
            WHERE id = ?
        """, (data['teacher_name'], message.text, data['teacher_id']))
        
        conn.commit()
        
        await message.answer(
            f"✅ Учитель успешно добавлен:\n"
            f"👤 {data['teacher_name']}\n"
            f"📚 Класс: {message.text}"
        )
        await state.clear()

@router.callback_query(F.data == "remove_teacher")
async def show_teachers_for_removal(callback: types.CallbackQuery):
    if callback.from_user.id != 6500936622:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
        
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, full_name, class 
            FROM users 
            WHERE role = 'teacher'
            ORDER BY class, full_name
        """)
        
        teachers = cursor.fetchall()
        
        if not teachers:
            await callback.message.edit_text("❌ Учителя не найдены")
            return
            
        kb = InlineKeyboardBuilder()
        
        for teacher_id, name, class_name in teachers:
            kb.button(
                text=f"{name} ({class_name})",
                callback_data=f"remove_teacher:{teacher_id}"
            )
            
        kb.button(text="◀️ Назад", callback_data="back_to_teacher_menu")
        kb.adjust(1)
        
        await callback.message.edit_text(
            "Выберите учителя для удаления:",
            reply_markup=kb.as_markup()
        )

@router.callback_query(F.data.startswith("remove_teacher:"))
async def remove_teacher(callback: types.CallbackQuery):
    if callback.from_user.id != 6500936622:
        await callback.answer("❌ Недостаточно прав", show_alert=True)
        return
        
    teacher_id = int(callback.data.split(":")[1])
    
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users 
            SET role = 'user',
                class = NULL
            WHERE id = ? AND role = 'teacher'
        """, (teacher_id,))
        
        conn.commit()
        
        await callback.answer("✅ Учитель удален из системы", show_alert=True)
        await show_teachers_for_removal(callback)

@router.callback_query(F.data == "list_teachers")
async def list_teachers(callback: types.CallbackQuery):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT full_name, class, 
                   (SELECT COUNT(*) FROM users u2 
                    WHERE u2.class = users.class 
                    AND u2.role = 'user') as students_count
            FROM users 
            WHERE role = 'teacher'
            ORDER BY class, full_name
        """)
        
        teachers = cursor.fetchall()
        
        if not teachers:
            await callback.message.edit_text(
                "❌ В системе пока нет учителей",
                reply_markup=InlineKeyboardBuilder().button(
                    text="◀️ Назад", 
                    callback_data="back_to_teacher_menu"
                ).as_markup()
            )
            return
            
        text = "📚 Список учителей:\n\n"
        
        for name, class_name, students in teachers:
            text += f"👤 {name}\n"
            text += f"📚 Класс: {class_name}\n"
            text += f"👥 Учеников: {students}\n\n"
            
        kb = InlineKeyboardBuilder()
        kb.button(text="◀️ Назад", callback_data="back_to_teacher_menu")
        
        await callback.message.edit_text(
            text,
            reply_markup=kb.as_markup()
        )

@router.callback_query(F.data == "back_to_teacher_menu")
async def back_to_teacher_menu(callback: types.CallbackQuery):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить учителя", callback_data="add_teacher")
    kb.button(text="➖ Удалить учителя", callback_data="remove_teacher")
    kb.button(text="📋 Список учителей", callback_data="list_teachers")
    kb.adjust(1)
    
    await callback.message.edit_text(
        "👨‍🏫 Управление учителями\n"
        "Выберите действие:",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "mass_issue")
async def start_mass_issue(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_student_qr)
    await callback.message.answer(
        "1️⃣ Сначала отсканируйте QR-код ученика или отправьте его ID"
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_student_qr)
async def process_student_qr(message: types.Message, state: FSMContext):
    try:
        student_id = None
        
        if message.photo:
            # Обработка QR-кода
            photo = await message.bot.get_file(message.photo[-1].file_id)
            photo_bytes = await message.bot.download_file(photo.file_path)
            nparr = np.frombuffer(photo_bytes.read(), np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            decoded_objects = decode(image)
            
            if not decoded_objects:
                await message.answer("❌ QR-код не найден. Попробуйте еще раз")
                return
                
            student_id = int(decoded_objects[0].data.decode('utf-8'))
        else:
            # Обработка ID
            student_id = int(message.text)
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем информацию о пользователе и его забронированных книгах
            cursor.execute("""
                SELECT 
                    u.full_name, 
                    u.class,
                    b.id as book_id,
                    b.title,
                    b.author,
                    r.id as reservation_id
                FROM users u
                LEFT JOIN book_reservations r ON u.id = r.user_id
                LEFT JOIN books b ON r.book_id = b.id
                WHERE u.id = ? AND r.status = 'pending'
            """, (student_id,))
            
            results = cursor.fetchall()
            if not results:
                await message.answer("❌ Пользователь не найден или у него нет забронированных книг")
                return

            student_name = results[0][0]
            student_class = results[0][1]
            
            # Создаем клавиатуру с забронированными книгами
            kb = InlineKeyboardBuilder()
            for _, _, book_id, title, author, reservation_id in results:
                if book_id:  # Проверяем, что есть забронированные книги
                    kb.button(
                        text=f"📖 {title} - {author}",
                        callback_data=f"select_book_{reservation_id}"
                    )
            kb.adjust(1)
            
            await state.update_data(student_id=student_id, student_name=student_name)
            await message.answer(
                f"2️⃣ Выбран читатель: {student_name} ({student_class})\n\n"
                f"Выберите книгу для выдачи:",
                reply_markup=kb.as_markup()
            )
            
            await state.set_state(AdminStates.waiting_for_book_selection)
            
    except ValueError:
        await message.answer("❌ Некорректный ID пользователя")
    except Exception as e:
        logging.error(f"Error processing student QR: {e}")
        await message.answer("❌ Произошла ошибка при обработке QR-кода")

@router.callback_query(AdminStates.waiting_for_book_selection, F.data.startswith("select_book_"))
async def process_book_selection(callback: types.CallbackQuery, state: FSMContext):
    reservation_id = int(callback.data.split("_")[2])
    
    await callback.message.answer(
        "3️⃣ Теперь отсканируйте QR-код экземпляра книги:"
    )
    await state.update_data(reservation_id=reservation_id)
    await state.set_state(AdminStates.waiting_for_book_qr)

@router.message(AdminStates.waiting_for_book_qr, F.photo)
async def process_book_qr(message: types.Message, state: FSMContext):
    try:
        # Скачиваем фото
        photo = await message.bot.get_file(message.photo[-1].file_id)
        photo_bytes = await message.bot.download_file(photo.file_path)
        
        # Конвертируем в формат для opencv
        nparr = np.frombuffer(photo_bytes.read(), np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Декодируем QR-код
        decoded_objects = decode(image)
        
        if not decoded_objects:
            await message.answer("❌ QR-код не найден. Попробуйте еще раз")
            return
            
        # Получаем ID экземпляра из QR-кода
        copy_id = decoded_objects[0].data.decode('utf-8')
        data = await state.get_data()
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем, что книга соответствует бронированию
            cursor.execute("""
                SELECT 
                    r.book_id,
                    b.title,
                    b.author
                FROM book_reservations r
                JOIN books b ON r.book_id = b.id
                WHERE r.id = ?
            """, (data['reservation_id'],))
            
            reservation = cursor.fetchone()
            if not reservation:
                await message.answer("❌ Бронирование не найдено")
                return
                
            # Проверяем, что экземпляр соответствует книге
            cursor.execute("""
                SELECT book_id, status
                FROM book_copies
                WHERE id = ?
            """, (copy_id,))
            
            copy = cursor.fetchone()
            if not copy:
                await message.answer("❌ Экземпляр книги не найден")
                return
                
            if copy[0] != reservation[0]:
                await message.answer(
                    "❌ Этот экземпляр не соответствует забронированной книге\n"
                    f"Нужна книга: {reservation[1]} ({reservation[2]})"
                )
                return
                
            if copy[1] != 'available':
                await message.answer("❌ Этот экземпляр уже выдан")
                return
                
            # Выдаем книгу
            cursor.execute("""
                INSERT INTO borrowed_books (
                    user_id, book_id, copy_id, reservation_id,
                    borrow_date, return_date, status
                ) VALUES (
                    ?, ?, ?, ?,
                    datetime('now'),
                    datetime('now', '+14 days'),
                    'borrowed'
                )
            """, (data['student_id'], reservation[0], copy_id, data['reservation_id']))
            
            # Обновляем статус бронирования
            cursor.execute("""
                UPDATE book_reservations
                SET status = 'completed'
                WHERE id = ?
            """, (data['reservation_id'],))
            
            conn.commit()
            
            await message.answer(
                f"✅ Книга выдана:\n"
                f"📖 {reservation[1]}\n"
                f"👤 {data['student_name']}\n"
                f"📅 Срок возврата: через 14 дней"
            )
            
            await state.clear()
            
    except Exception as e:
        logging.error(f"Error processing book QR: {e}")
        await message.answer("❌ Произошла ошибка при обработке QR-кода")

@router.callback_query(F.data == "mass_return")
async def start_mass_return(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.waiting_for_return_books)
    await state.update_data(returned_books=[])  # Инициализируем список возвращаемых книг
    
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Завершить возврат", callback_data="finish_mass_return")
    kb.button(text="❌ Отменить", callback_data="cancel_mass_return")
    kb.adjust(1)
    
    await callback.message.answer(
        "📚 Массовый возврат книг\n\n"
        "Сканируйте QR-коды книг по одной.\n"
        "После завершения нажмите 'Завершить возврат'",
        reply_markup=kb.as_markup()
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_return_books, F.photo)
async def process_book_for_mass_return(message: types.Message, state: FSMContext):
    try:
        # Получаем фото и декодируем QR
        photo = await message.bot.get_file(message.photo[-1].file_id)
        photo_bytes = await message.bot.download_file(photo.file_path)
        nparr = np.frombuffer(photo_bytes.read(), np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        decoded_objects = decode(image)
        
        if not decoded_objects:
            await message.answer("❌ QR-код не найден. Попробуйте еще раз")
            return
            
        copy_id = decoded_objects[0].data.decode('utf-8')
        data = await state.get_data()
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем книгу
            cursor.execute("""
                SELECT 
                    b.title,
                    b.author,
                    u.full_name,
                    u.id as user_id,
                    bb.id as borrow_id
                FROM book_copies bc
                JOIN books b ON bc.book_id = b.id
                JOIN borrowed_books bb ON bc.id = bb.copy_id
                JOIN users u ON bb.user_id = u.id
                WHERE bc.id = ? AND bb.status = 'borrowed'
            """, (copy_id,))
            
            book = cursor.fetchone()
            if not book:
                await message.answer("❌ Эта книга не числится на руках")
                return
                
            title, author, student_name, student_id, borrow_id = book
            
            # Проверяем, не добавили ли мы уже эту книгу в список
            returned_books = data.get('returned_books', [])
            if any(b['copy_id'] == copy_id for b in returned_books):
                await message.answer("❌ Эта книга уже добавлена в список")
                return
            
            # Добавляем книгу в список
            returned_books.append({
                'copy_id': copy_id,
                'borrow_id': borrow_id,
                'title': title,
                'author': author,
                'student_name': student_name,
                'student_id': student_id
            })
            
            await state.update_data(returned_books=returned_books)
            
            # Группируем книги по ученикам
            students = {}
            for book in returned_books:
                if book['student_id'] not in students:
                    students[book['student_id']] = {
                        'name': book['student_name'],
                        'books': []
                    }
                students[book['student_id']]['books'].append(f"📖 {book['title']}")
            
            # Формируем текст со списком
            text = "📚 Отсканированные книги:\n\n"
            for student_id, info in students.items():
                text += f"👤 {info['name']}:\n"
                text += "\n".join(info['books'])
                text += "\n\n"
            
            kb = InlineKeyboardBuilder()
            kb.button(text="✅ Завершить возврат", callback_data="finish_mass_return")
            kb.button(text="❌ Отменить", callback_data="cancel_mass_return")
            kb.adjust(1)
            
            await message.answer(
                text + "Продолжайте сканировать книги или нажмите 'Завершить возврат'",
                reply_markup=kb.as_markup()
            )
            
    except Exception as e:
        logging.error(f"Error in process_book_for_mass_return: {e}")
        await message.answer("❌ Произошла ошибка при сканировании книги")

@router.callback_query(F.data == "finish_mass_return")
async def finish_mass_return(callback: types.CallbackQuery, state: FSMContext):
    try:
        data = await state.get_data()
        returned_books = data.get('returned_books', [])
        
        if not returned_books:
            await callback.answer("❌ Не отсканировано ни одной книги", show_alert=True)
            return
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Начинаем транзакцию
            cursor.execute("BEGIN")
            
            try:
                for book in returned_books:
                    # Обновляем статус в borrowed_books
                    cursor.execute("""
                        UPDATE borrowed_books 
                        SET status = 'returned' 
                        WHERE id = ?
                    """, (book['borrow_id'],))
                
                conn.commit()
                
                # Группируем книги по ученикам для уведомлений
                students = {}
                for book in returned_books:
                    if book['student_id'] not in students:
                        students[book['student_id']] = {
                            'name': book['student_name'],
                            'books': []
                        }
                    students[book['student_id']]['books'].append(book['title'])
                
                # Отправляем уведомления ученикам
                for student_id, info in students.items():
                    try:
                        await callback.bot.send_message(
                            student_id,
                            f"📚 Возвращены книги:\n\n" +
                            "\n".join(f"📖 {title}" for title in info['books']) +
                            "\n\nСпасибо, что пользуетесь библиотекой! 😊"
                        )
                    except Exception as e:
                        logging.error(f"Error sending notification to student: {e}")
                
                # Формируем итоговый отчет
                text = "✅ Книги успешно возвращены:\n\n"
                for student_id, info in students.items():
                    text += f"👤 {info['name']}:\n"
                    text += "\n".join(f"📖 {title}" for title in info['books'])
                    text += "\n\n"
                
                await callback.message.edit_text(text)
                
            except Exception as e:
                cursor.execute("ROLLBACK")
                raise e
                
        await state.clear()
        
    except Exception as e:
        logging.error(f"Error in finish_mass_return: {e}")
        await callback.answer("❌ Произошла ошибка при возврате книг", show_alert=True)

@router.callback_query(F.data == "cancel_mass_return")
async def cancel_mass_return(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Возврат книг отменен")

# Этот обработчик перехватывает ВСЕ callbacks и мешает работе остальных
# Временно закомментируем его для отладки
# @router.callback_query()
async def log_all_callbacks(callback: types.CallbackQuery):
    logging.warning(f"DEBUG: Получен callback: {callback.data}")
    # Позволяем обработку продолжиться
    return False 