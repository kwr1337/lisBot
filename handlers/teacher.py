from aiogram import Router, types, F
from aiogram.filters import Command
from database.models import get_db
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime
from aiogram.fsm.context import FSMContext
from states.teacher_states import TeacherStates
import numpy as np
import cv2
from pyzbar.pyzbar import decode

router = Router()

def get_teacher_keyboard():
    keyboard = [
        [
            types.KeyboardButton(text="👥 Управление классом"),
            types.KeyboardButton(text="📚 Книги учеников")
        ],
        [
            types.KeyboardButton(text="📊 Должники"),
            types.KeyboardButton(text="👤 Мой профиль")
        ],
        [
            types.KeyboardButton(text="◀️ Выйти из панели учителя")
        ]
    ]
    
    return types.ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )

@router.message(F.text == "👥 Мой класс")
async def show_class_students(message: types.Message):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT class FROM users WHERE id = ? AND role = 'teacher'
            """, (message.from_user.id,))
            
            teacher = cursor.fetchone()
            if not teacher:
                return
                
            teacher_class = teacher[0]
            
            # Получаем список учеников класса
            cursor.execute("""
                SELECT id, full_name, phone
                FROM users 
                WHERE class = ? AND role = 'user'
                ORDER BY full_name
            """, (teacher_class,))
            
            students = cursor.fetchall()
            
            if not students:
                await message.answer(f"В классе {teacher_class} пока нет учеников")
                return
                
            text = f"📚 Ученики {teacher_class} класса:\n\n"
            for student_id, name, phone in students:
                text += f"👤 {name}\n"
                text += f"📱 {phone}\n"
                
                # Считаем книги на руках
                cursor.execute("""
                    SELECT COUNT(*) FROM borrowed_books 
                    WHERE user_id = ? AND status = 'borrowed'
                """, (student_id,))
                books_count = cursor.fetchone()[0]
                
                text += f"📚 Книг на руках: {books_count}\n\n"
            
            await message.answer(text)
            
    except Exception as e:
        logging.error(f"Error in show_class_students: {e}")
        await message.answer("❌ Произошла ошибка при получении списка класса")

@router.message(F.text == "📚 Книги учеников")
async def show_students_books(message: types.Message, state: FSMContext):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем класс учителя
            cursor.execute("""
                SELECT class FROM users WHERE id = ? AND role = 'teacher'
            """, (message.from_user.id,))
            
            teacher = cursor.fetchone()
            if not teacher:
                return
                
            teacher_class = teacher[0]
            
            # Получаем список учеников класса
            cursor.execute("""
                SELECT id, full_name
                FROM users 
                WHERE class = ? AND role = 'user'
                ORDER BY full_name
            """, (teacher_class,))
            
            students = cursor.fetchall()
            
            if not students:
                await message.answer(f"В классе {teacher_class} пока нет учеников")
                return
            
            # Сохраняем список учеников в состоянии
            await state.update_data(students=students, page=0)
            await show_students_page(message, state)
            
    except Exception as e:
        logging.error(f"Error in show_students_books: {e}")
        await message.answer("❌ Произошла ошибка при получении списка учеников")

async def show_students_page(message: types.Message, state: FSMContext):
    data = await state.get_data()
    students = data.get('students', [])
    page = data.get('page', 0)
    
    # Пагинация по 5 учеников
    start = page * 5
    end = start + 5
    students_page = students[start:end]
    
    if not students_page:
        await message.answer("Нет больше учеников на этой странице.")
        return
    
    kb = InlineKeyboardBuilder()
    for student_id, full_name in students_page:
        kb.button(text=full_name, callback_data=f"view_student_books:{student_id}")
    
    if start > 0:
        kb.button(text="⬅️ Назад", callback_data="prev_students_page")
    if end < len(students):
        kb.button(text="➡️ Вперед", callback_data="next_students_page")
    
    kb.adjust(1)
    
    await message.answer("Выберите ученика для просмотра книг:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("view_student_books:"))
async def view_student_books(callback: types.CallbackQuery, state: FSMContext):
    student_id = int(callback.data.split(":")[1])
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем книги ученика
        cursor.execute("""
            SELECT 
                b.title,
                b.author,
                bb.borrow_date,
                bb.return_date,
                bb.is_textbook
            FROM borrowed_books bb
            JOIN books b ON bb.book_id = b.id
            WHERE bb.user_id = ? AND bb.status = 'borrowed'
            ORDER BY bb.is_textbook, bb.borrow_date
        """, (student_id,))
        
        books = cursor.fetchall()
        
        if not books:
            await callback.message.edit_text("У ученика нет книг на руках.")
            return
        
        text = "📚 Книги ученика:\n\n"
        textbooks = []
        regular_books = []
        
        for title, author, borrow_date, return_date, is_textbook in books:
            try:
                # Обрабатываем дату с возможными миллисекундами
                try:
                    borrow = datetime.strptime(borrow_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                except ValueError:
                    # Если не получилось, пробуем формат с миллисекундами
                    borrow = datetime.strptime(borrow_date.split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                
                try:
                    return_date_formatted = datetime.strptime(return_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                except ValueError:
                    # Если не получилось, пробуем формат с миллисекундами
                    return_date_formatted = datetime.strptime(return_date.split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                
                book_info = (
                    f"📖 {title}\n"
                    f"✍️ {author}\n"
                    f"📅 Взята: {borrow}\n"
                    f"📅 Вернуть до: {return_date_formatted}\n\n"
                )
                
                if is_textbook:
                    textbooks.append(book_info)
                else:
                    regular_books.append(book_info)
            except Exception as date_error:
                logging.error(f"Error formatting date for book {title}: {date_error}")
                # В случае ошибки просто выводим книгу без дат
                book_info = (
                    f"📖 {title}\n"
                    f"✍️ {author}\n\n"
                )
                if is_textbook:
                    textbooks.append(book_info)
                else:
                    regular_books.append(book_info)
        
        if regular_books:
            text += "Обычные книги:\n" + "".join(regular_books) + "\n"
        if textbooks:
            text += "Учебники:\n" + "".join(textbooks)
        
        kb = InlineKeyboardBuilder()
        kb.button(text="◀️ Назад", callback_data="back_to_students_list")
        
        await callback.message.edit_text(text, reply_markup=kb.as_markup())

@router.callback_query(F.data == "back_to_students_list")
async def back_to_students_list(callback: types.CallbackQuery, state: FSMContext):
    await show_students_page(callback.message, state)

@router.callback_query(F.data == "next_students_page")
async def next_students_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data.get('page', 0)
    await state.update_data(page=page + 1)
    await show_students_page(callback.message, state)

@router.callback_query(F.data == "prev_students_page")
async def prev_students_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data.get('page', 0)
    await state.update_data(page=page - 1)
    await show_students_page(callback.message, state)

@router.message(Command("teacher"))
async def teacher_panel(message: types.Message):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT role FROM users 
                WHERE id = ? AND role = 'teacher'
            """, (message.from_user.id,))
            
            if not cursor.fetchone():
                await message.answer("❌ У вас нет прав учителя")
                return
            
            await message.answer(
                "👨‍🏫 Панель учителя\n\n"
                "Выберите нужное действие:",
                reply_markup=get_teacher_keyboard()
            )
            
    except Exception as e:
        logging.error(f"Error in teacher_panel: {e}")
        await message.answer("❌ Произошла ошибка при открытии панели учителя")

@router.message(F.text == "◀️ Выйти из панели учителя")
async def return_to_user_menu(message: types.Message):
    from handlers.user import get_main_keyboard
    
    await message.answer(
        "Вы вернулись в обычное меню",
        reply_markup=get_main_keyboard()
    )

@router.message(F.text == "👥 Управление классом")
async def manage_class(message: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить ученика", callback_data="add_student")
    kb.button(text="➖ Удалить ученика", callback_data="remove_student")
    kb.button(text="📋 Список класса", callback_data="class_list")
    kb.adjust(1)
    
    await message.answer(
        "👥 Управление классом\n"
        "Выберите действие:",
        reply_markup=kb.as_markup()
    )

@router.callback_query(F.data == "add_student")
async def start_add_student(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "Добавление ученика в класс\n\n"
        "Вы можете:\n"
        "1. Отправить ID ученика\n"
        "2. Отправить фото QR-кода из профиля ученика\n\n"
        "Отправьте ID или фото QR-кода:"
    )
    await state.set_state(TeacherStates.waiting_for_student_id)
    await callback.answer()

@router.message(TeacherStates.waiting_for_student_id)
async def process_student_input(message: types.Message, state: FSMContext):
    try:
        if message.photo:
            # Если прислали фото, обрабатываем QR-код
            photo = await message.bot.get_file(message.photo[-1].file_id)
            photo_bytes = await message.bot.download_file(photo.file_path)
            
            nparr = np.frombuffer(photo_bytes.read(), np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            decoded_objects = decode(image)
            
            if not decoded_objects:
                await message.answer(
                    "❌ QR-код не найден.\n\n"
                    "Убедитесь, что:\n"
                    "• QR-код хорошо освещен\n"
                    "• Изображение не размыто\n"
                    "• QR-код полностью попадает в кадр\n\n"
                    "Попробуйте еще раз или отправьте ID ученика:"
                )
                return
                
            student_id = int(decoded_objects[0].data.decode('utf-8'))
        else:
            # Если прислали текст, пробуем получить ID
            student_id = int(message.text)
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверяем, что отправитель - учитель
            cursor.execute("""
                SELECT class FROM users 
                WHERE id = ? AND role = 'teacher'
            """, (message.from_user.id,))
            
            teacher = cursor.fetchone()
            if not teacher:
                await message.answer("❌ У вас нет прав учителя")
                return
                
            teacher_class = teacher[0]
            
            # Проверяем ученика
            cursor.execute("""
                SELECT id, class, full_name FROM users WHERE id = ?
            """, (student_id,))
            
            student = cursor.fetchone()
            if not student:
                await message.answer("❌ Пользователь не найден в базе данных")
                return
                
            if student[1]:
                await message.answer(f"❌ Ученик {student[2]} уже в {student[1]} классе")
                return
            
            # Добавляем ученика в класс
            cursor.execute("""
                UPDATE users 
                SET class = ?
                WHERE id = ?
            """, (teacher_class, student_id))
            
            conn.commit()
            
            await message.answer(
                f"✅ Ученик {student[2]} добавлен в {teacher_class} класс"
            )
            await state.clear()
            
    except ValueError:
        await message.answer(
            "❌ Некорректный ID ученика\n"
            "Отправьте числовой ID или фото QR-кода:"
        )
    except Exception as e:
        logging.error(f"Error adding student: {e}")
        await message.answer(
            "❌ Произошла ошибка при добавлении ученика\n"
            "Попробуйте еще раз:"
        )

@router.callback_query(F.data == "remove_student")
async def show_students_for_removal(callback: types.CallbackQuery):
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем класс учителя
        cursor.execute("""
            SELECT class FROM users 
            WHERE id = ? AND role = 'teacher'
        """, (callback.from_user.id,))
        
        teacher = cursor.fetchone()
        if not teacher:
            await callback.answer("❌ У вас нет прав учителя", show_alert=True)
            return
            
        teacher_class = teacher[0]
        
        # Получаем список учеников
        cursor.execute("""
            SELECT id, full_name 
            FROM users 
            WHERE class = ? AND role = 'user'
            ORDER BY full_name
        """, (teacher_class,))
        
        students = cursor.fetchall()
        
        if not students:
            await callback.message.edit_text(
                f"В классе {teacher_class} пока нет учеников"
            )
            return
            
        kb = InlineKeyboardBuilder()
        
        for student_id, name in students:
            kb.button(
                text=f"❌ {name}",
                callback_data=f"remove_student:{student_id}"
            )
            
        kb.button(text="◀️ Назад", callback_data="back_to_class_menu")
        kb.adjust(1)
        
        await callback.message.edit_text(
            "Выберите ученика для удаления из класса:",
            reply_markup=kb.as_markup()
        )

@router.callback_query(F.data.startswith("remove_student:"))
async def remove_student(callback: types.CallbackQuery):
    student_id = int(callback.data.split(":")[1])
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Проверяем, что это ученик из класса этого учителя
        cursor.execute("""
            SELECT t.class 
            FROM users s
            JOIN users t ON s.class = t.class
            WHERE s.id = ? AND t.id = ? AND t.role = 'teacher'
        """, (student_id, callback.from_user.id))
        
        if not cursor.fetchone():
            await callback.answer("❌ Этот ученик не из вашего класса", show_alert=True)
            return
        
        # Удаляем ученика из класса
        cursor.execute("""
            UPDATE users 
            SET class = NULL
            WHERE id = ?
        """, (student_id,))
        
        conn.commit()
        
        await callback.answer("✅ Ученик удален из класса", show_alert=True)
        await show_students_for_removal(callback)

@router.message(F.text == "📊 Должники")
async def show_debtors(message: types.Message, state: FSMContext):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем класс учителя
            cursor.execute("""
                SELECT class FROM users WHERE id = ? AND role = 'teacher'
            """, (message.from_user.id,))
            
            teacher = cursor.fetchone()
            if not teacher:
                return
                
            teacher_class = teacher[0]
            
            # Получаем список должников
            cursor.execute("""
                SELECT DISTINCT u.id, u.full_name
                FROM users u
                JOIN borrowed_books bb ON u.id = bb.user_id
                WHERE u.class = ? AND u.role = 'user' AND bb.status = 'borrowed' AND bb.return_date < date('now')
                ORDER BY u.full_name
            """, (teacher_class,))
            
            debtors = cursor.fetchall()
            
            if not debtors:
                await message.answer(f"В классе {teacher_class} нет должников")
                return
            
            # Сохраняем список должников в состоянии
            await state.update_data(debtors=debtors, page=0)
            await show_debtors_page(message, state)
            
    except Exception as e:
        logging.error(f"Error in show_debtors: {e}")
        await message.answer("❌ Произошла ошибка при получении списка должников")

async def show_debtors_page(message: types.Message, state: FSMContext):
    data = await state.get_data()
    debtors = data.get('debtors', [])
    page = data.get('page', 0)
    
    # Пагинация по 5 должников
    start = page * 5
    end = start + 5
    debtors_page = debtors[start:end]
    
    if not debtors_page:
        await message.answer("Нет больше должников на этой странице.")
        return
    
    kb = InlineKeyboardBuilder()
    for debtor_id, full_name in debtors_page:
        kb.button(text=full_name, callback_data=f"view_debtor_books:{debtor_id}")
    
    if start > 0:
        kb.button(text="⬅️ Назад", callback_data="prev_debtors_page")
    if end < len(debtors):
        kb.button(text="➡️ Вперед", callback_data="next_debtors_page")
    
    kb.adjust(1)
    
    await message.answer("Выберите должника для просмотра просроченных книг:", reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("view_debtor_books:"))
async def view_debtor_books(callback: types.CallbackQuery, state: FSMContext):
    debtor_id = int(callback.data.split(":")[1])
    
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Получаем просроченные книги должника
        cursor.execute("""
            SELECT 
                b.title,
                b.author,
                bb.borrow_date,
                bb.return_date
            FROM borrowed_books bb
            JOIN books b ON bb.book_id = b.id
            WHERE bb.user_id = ? AND bb.status = 'borrowed' AND bb.return_date < date('now')
            ORDER BY bb.borrow_date
        """, (debtor_id,))
        
        books = cursor.fetchall()
        
        if not books:
            await callback.message.edit_text("У должника нет просроченных книг.")
            return
        
        text = "📚 Просроченные книги:\n\n"
        
        for title, author, borrow_date, return_date in books:
            try:
                # Обрабатываем дату с возможными миллисекундами
                try:
                    borrow = datetime.strptime(borrow_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                except ValueError:
                    # Если не получилось, пробуем формат с миллисекундами
                    borrow = datetime.strptime(borrow_date.split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                
                try:
                    return_date_formatted = datetime.strptime(return_date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                except ValueError:
                    # Если не получилось, пробуем формат с миллисекундами
                    return_date_formatted = datetime.strptime(return_date.split(".")[0], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y")
                
                text += (
                    f"📖 {title}\n"
                    f"✍️ {author}\n"
                    f"📅 Взята: {borrow}\n"
                    f"📅 Вернуть до: {return_date_formatted}\n\n"
                )
            except Exception as date_error:
                logging.error(f"Error formatting date for book {title}: {date_error}")
                # В случае ошибки просто выводим книгу без дат
                text += (
                    f"📖 {title}\n"
                    f"✍️ {author}\n\n"
                )
        
        kb = InlineKeyboardBuilder()
        kb.button(text="◀️ Назад", callback_data="back_to_debtors_list")
        
        await callback.message.edit_text(text, reply_markup=kb.as_markup())

@router.callback_query(F.data == "back_to_debtors_list")
async def back_to_debtors_list(callback: types.CallbackQuery, state: FSMContext):
    await show_debtors_page(callback.message, state)

@router.callback_query(F.data == "next_debtors_page")
async def next_debtors_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data.get('page', 0)
    await state.update_data(page=page + 1)
    await show_debtors_page(callback.message, state)

@router.callback_query(F.data == "prev_debtors_page")
async def prev_debtors_page(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    page = data.get('page', 0)
    await state.update_data(page=page - 1)
    await show_debtors_page(callback.message, state)

@router.callback_query(F.data.startswith("class_books_page_"))
async def process_class_books_pagination(callback: types.CallbackQuery, state: FSMContext):
    page = int(callback.data.split("_")[-1])
    
    # Получаем данные о классе из состояния
    data = await state.get_data()
    class_name = data.get("selected_class")
    
    if not class_name:
        await callback.answer("Ошибка: класс не выбран")
        return
    
    # Получаем список книг для класса с пагинацией
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем общее количество книг
            cursor.execute("""
                SELECT COUNT(DISTINCT bb.id)
                FROM borrowed_books bb
                JOIN users u ON bb.user_id = u.id
                WHERE u.class = ? AND bb.status = 'borrowed'
            """, (class_name,))
            
            total_books = cursor.fetchone()[0]
            
            # Получаем книги для текущей страницы
            cursor.execute("""
                SELECT 
                    u.full_name,
                    b.title,
                    b.author,
                    bb.borrow_date,
                    bb.return_date,
                    bb.id
                FROM borrowed_books bb
                JOIN users u ON bb.user_id = u.id
                JOIN book_copies bc ON bb.copy_id = bc.id
                JOIN books b ON bc.book_id = b.id
                WHERE u.class = ? AND bb.status = 'borrowed'
                ORDER BY u.full_name, b.title
                LIMIT ? OFFSET ?
            """, (class_name, BOOKS_PER_PAGE, (page - 1) * BOOKS_PER_PAGE))
            
            books = cursor.fetchall()
            
            # Формируем сообщение
            if not books:
                text = f"📚 Ученики класса {class_name} не взяли ни одной книги"
            else:
                text = f"📚 Книги учеников класса {class_name} (страница {page}):\n\n"
                
                for i, (student_name, title, author, borrow_date, return_date, book_id) in enumerate(books, start=1):
                    borrow_date_str = datetime.fromisoformat(borrow_date).strftime("%d.%m.%Y")
                    return_date_str = datetime.fromisoformat(return_date).strftime("%d.%m.%Y")
                    
                    text += f"{i}. {student_name}\n"
                    text += f"   📖 {title} - {author}\n"
                    text += f"   📅 Взята: {borrow_date_str}, вернуть до: {return_date_str}\n\n"
            
            # Создаем клавиатуру с пагинацией
            kb = InlineKeyboardBuilder()
            
            # Добавляем кнопки пагинации
            if page > 1:
                kb.button(text="◀️ Назад", callback_data=f"class_books_page_{page-1}")
            
            if page * BOOKS_PER_PAGE < total_books:
                kb.button(text="Вперед ▶️", callback_data=f"class_books_page_{page+1}")
            
            kb.button(text="🔙 Назад к классам", callback_data="back_to_classes")
            kb.adjust(2, 1)
            
            await callback.message.edit_text(
                text,
                reply_markup=kb.as_markup()
            )
            
            await callback.answer("Страница обновлена")
            
    except Exception as e:
        logging.error(f"Error in process_class_books_pagination: {e}")
        await callback.message.answer("❌ Произошла ошибка при получении списка книг") 