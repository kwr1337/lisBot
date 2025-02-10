import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.models import get_db, create_book_copies, log_admin_action
from states.admin_states import AdminStates, AdminManageStates
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
import secrets
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, Message
from utils.token_storage import add_token, remove_token
import cv2
import numpy as np
from pyzbar.pyzbar import decode
import io
from PIL import Image
import logging

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

# Регистрируем фильтр для всех админских команд
router.message.filter(admin_filter)

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
                KeyboardButton(text="◀️ Выйти из панели админа")
            ]
        ],
        resize_keyboard=True
    )
    return keyboard

@router.message(Command("admin"))
async def admin_panel(message: types.Message):
    if not await check_admin(message):
        await message.answer("⛔️ У вас нет прав администратора")
        return
        
    await message.answer(
        "🔐 Панель администратора\n\n"
        "Выберите нужное действие:",
        reply_markup=get_admin_keyboard()
    )

@router.message(F.text == "🔍 Сканировать QR")
async def scan_qr_command(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="📤 Выдать книгу", callback_data="scan_issue")
    kb.button(text="📥 Вернуть книгу", callback_data="scan_return")
    # kb.button(text="◀️ Назад", callback_data="admin")
    kb.adjust(2, 1)
    
    await message.answer(
        "📷 Выберите действие для сканирования QR-кода:",
        reply_markup=kb.as_markup()
    )

@router.message(F.text == "🌐 Веб-панель")
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

@router.callback_query(F.data.in_({"scan_issue", "scan_return"}))
async def prepare_for_scan(callback: types.CallbackQuery, state: FSMContext):
    action = callback.data
    await state.update_data(scan_action=action)
    
    await callback.message.edit_text(
        "📸 Отправьте фотографию QR-кода книги.\n\n"
        "Для этого:\n"
        "1. Нажмите на скрепку 📎\n"
        "2. Выберите или сделайте фото\n"
        "3. Убедитесь, что QR-код хорошо виден"
    )
    await state.set_state(AdminStates.waiting_for_qr)
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
            
        # Получаем ID книги из QR-кода
        book_id = decoded_objects[0].data.decode('utf-8')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем книгу
            cursor.execute("""
                SELECT b.title, b.author, bc.id as copy_id, bc.status,
                       bb.user_id, bb.status as borrow_status,
                       u.full_name, u.username
                FROM books b
                JOIN book_copies bc ON b.id = bc.book_id
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id 
                    AND bb.status = 'booked'
                LEFT JOIN users u ON bb.user_id = u.id
                WHERE bc.id = ?
            """, (book_id,))
            
            book_info = cursor.fetchone()
            if not book_info:
                await message.answer("❌ Книга не найдена в базе данных")
                await state.clear()
                return
                
            title, author, copy_id, status, user_id, borrow_status, user_full_name, username = book_info
            display_name = user_full_name or f"@{username}" if user_full_name or username else "Нет данных"
            
            # Получаем действие из состояния
            data = await state.get_data()
            action = data.get('scan_action')
            
            if action == 'scan_issue':
                if not borrow_status or borrow_status != 'booked':
                    await message.answer(
                        "❌ Эта книга не забронирована.\n"
                        "Выдача возможна только предварительно забронированных книг."
                    )
                    return
                    
                # Выдаем книгу
                return_date = datetime.now() + timedelta(days=14)
                cursor.execute("""
                    UPDATE book_copies 
                    SET status = 'borrowed' 
                    WHERE id = ?
                """, (copy_id,))
                
                cursor.execute("""
                    UPDATE borrowed_books 
                    SET status = 'borrowed',
                        borrow_date = datetime('now', 'localtime'),
                        return_date = datetime(?, 'localtime')
                    WHERE copy_id = ? AND status = 'booked'
                """, (return_date.strftime("%Y-%m-%d %H:%M:%S"), copy_id))
                
                conn.commit()
                
                # Уведомляем админа
                await message.answer(
                    f"✅ Книга успешно выдана:\n"
                    f"📖 {title}\n"
                    f"✍️ {author}\n"
                    f"👤 Читатель: {display_name}\n"
                    f"📅 Вернуть до: {return_date.strftime('%d.%m.%Y')}"
                )
                
                # Уведомляем пользователя
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
                
            elif action == 'scan_return':
                if status != 'borrowed':
                    await message.answer("❌ Эта книга не числится как выданная")
                    return
                    
                # Получаем информацию о пользователе перед возвратом
                cursor.execute("""
                    SELECT u.full_name, u.username, bb.user_id
                    FROM borrowed_books bb
                    JOIN users u ON bb.user_id = u.id
                    WHERE bb.copy_id = ? AND bb.status = 'borrowed'
                    ORDER BY bb.id DESC LIMIT 1
                """, (copy_id,))
                
                user_info = cursor.fetchone()
                if user_info:
                    user_full_name, username, user_id = user_info
                    display_name = user_full_name or f"@{username}"
                else:
                    display_name = "Нет данных"
                    user_id = None
                
                # Возвращаем книгу
                return_date = datetime.now()
                cursor.execute("""
                    UPDATE book_copies 
                    SET status = 'available' 
                    WHERE id = ?
                """, (copy_id,))
                
                cursor.execute("""
                    UPDATE borrowed_books 
                    SET status = 'returned',
                        return_date = datetime('now', 'localtime')
                    WHERE copy_id = ? AND status = 'borrowed'
                """, (copy_id,))
                
                conn.commit()
                
                # Уведомляем админа
                await message.answer(
                    f"✅ Книга успешно возвращена:\n"
                    f"📖 {title}\n"
                    f"✍️ {author}\n"
                    f"👤 Читатель: {display_name}\n"
                    f"📅 Дата возврата: {return_date.strftime('%d.%m.%Y')}"
                )
                
                # Уведомляем пользователя
                if user_id:
                    try:
                        await message.bot.send_message(
                            user_id,
                            f"📚 Вы вернули книгу:\n"
                            f"📖 {title}\n"
                            f"✍️ {author}\n"
                            f"📅 Дата возврата: {return_date.strftime('%d.%m.%Y')}\n\n"
                            f"Спасибо, что пользуетесь нашей библиотекой! 😊"
                        )
                    except Exception as e:
                        logging.error(f"Error sending notification to user: {e}")
                
            await state.clear()
                
    except Exception as e:
        logging.error(f"Error processing QR: {e}")
        await message.answer("❌ Произошла ошибка при обработке QR-кода")
        await state.clear()

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