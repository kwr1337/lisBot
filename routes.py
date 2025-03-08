from database.models import get_db, log_admin_action
from datetime import datetime
import logging
from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
import json
from utils.token_storage import verify_token
import qrcode
from io import BytesIO
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter

# Создаем router с префиксом
router = APIRouter(prefix="")
templates = Jinja2Templates(directory="admin_panel/templates")
router.mount("/static", StaticFiles(directory="admin_panel/static"), name="static")

def is_admin(request: Request) -> bool:
    return request.session.get('is_admin', False)

def get_admin_info(request: Request) -> dict:
    return {
        'username': request.session.get('username', 'Admin'),
        'user_id': request.session.get('user_id')
    }

@router.post("/books/{book_id}/edit")
async def edit_book(
    request: Request,
    book_id: int,
    title: str = Form(...),
    author: str = Form(...),
    description: str = Form(...),
    quantity: int = Form(...)
):
    try:
        admin_id = request.session.get('user_id')
        logging.info(f"Edit book request - Session data: {dict(request.session)}")
        
        if not admin_id:
            logging.error("No admin_id in session")
            return RedirectResponse(url="/login")
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, username, role FROM users WHERE id = ?", (admin_id,))
        user = cursor.fetchone()
        logging.info(f"User data: {user}")
        
        if not user or user[2] != 'admin':
            logging.error(f"User {admin_id} is not admin")
            return RedirectResponse(url="/login")
        
        cursor.execute("SELECT title, author FROM books WHERE id = ?", (book_id,))
        old_book = cursor.fetchone()
        logging.info(f"Book data: {old_book}")
        
        if not old_book:
            raise HTTPException(status_code=404, detail="Book not found")
        
        old_title, old_author = old_book
        
        cursor.execute("""
            UPDATE books 
            SET title = ?, author = ?, description = ?, quantity = ?
            WHERE id = ?
        """, (title, author, description, quantity, book_id))
        
        details = f"Изменена книга: '{old_title}' -> '{title}', '{old_author}' -> '{author}'"
        logging.info(f"Attempting to log action with details: {details}")
        
        log_admin_action(
            admin_id=admin_id,
            action_type="edit_book",
            book_id=book_id,
            details=details
        )
        
        conn.commit()
        
        cursor.execute("SELECT * FROM admin_logs ORDER BY id DESC LIMIT 1")
        last_log = cursor.fetchone()
        logging.info(f"Last log entry: {last_log}")
        
        return RedirectResponse(url="/books", status_code=303)
        
    except Exception as e:
        logging.error(f"Error in edit_book: {e}")
        logging.exception("Full traceback:")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if 'conn' in locals():
            conn.close()

@router.post("/books/add")
async def add_book(
    request: Request,
    title: str = Form(...),
    author: str = Form(...),
    theme: str = Form(...),
    description: str = Form(...),
    pages: str = Form(...),
    edition_number: str = Form(None),
    publication_year: str = Form(...),
    publisher: str = Form(...),
    quantity: int = Form(...)
):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Проверка и добавление отсутствующих столбцов
            cursor.execute("PRAGMA table_info(books)")
            columns = [column[1] for column in cursor.fetchall()]
            
            # Добавляем недостающие столбцы
            if 'pages' not in columns:
                cursor.execute("ALTER TABLE books ADD COLUMN pages INTEGER")
            if 'edition_number' not in columns:
                cursor.execute("ALTER TABLE books ADD COLUMN edition_number TEXT")
            if 'publication_year' not in columns:
                cursor.execute("ALTER TABLE books ADD COLUMN publication_year INTEGER")
            if 'publisher' not in columns:
                cursor.execute("ALTER TABLE books ADD COLUMN publisher TEXT")
            if 'theme' not in columns:
                cursor.execute("ALTER TABLE books ADD COLUMN theme TEXT")
            conn.commit()
            
            cursor.execute("""
                INSERT INTO books (
                    title, author, theme, description, 
                    pages, edition_number, publication_year, publisher, quantity
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                title, author, theme, description,
                int(pages), edition_number, int(publication_year), publisher, quantity
            ))
            
            book_id = cursor.lastrowid
            
            # Сначала фиксируем текущую транзакцию
            conn.commit()
            
            admin_id = request.session.get('user_id')
            log_admin_action(
                admin_id=admin_id,
                action_type="add_book",
                book_id=book_id,
                details=f"Added book: '{title}' by {author}"
            )
            
        return RedirectResponse(url="/books", status_code=303)
    except Exception as e:
        logging.error(f"Error adding book: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/books/{book_id}/delete")
async def delete_book(request: Request, book_id: int):
    try:
        admin_id = request.session.get('user_id')
        if not admin_id:
            return RedirectResponse(url="/login", status_code=302)
            
        with get_db() as conn:
            cursor = conn.cursor()
            
            cursor.execute("SELECT role FROM users WHERE id = ?", (admin_id,))
            result = cursor.fetchone()
            if not result or result[0] != 'admin': 
                return RedirectResponse(url="/login", status_code=302)
            
            # Получаем информацию о книге перед удалением
            cursor.execute("SELECT title, author FROM books WHERE id = ?", (book_id,))
            book = cursor.fetchone()
            if book:  
                title, author = book
                
                cursor.execute("DELETE FROM books WHERE id = ?", (book_id,))
                conn.commit()
                
                # Логируем действие
                log_admin_action(
                    admin_id=admin_id,
                    action_type="delete_book",
                    book_id=book_id,
                    details=f"Удалена книга: '{title}' by {author}"
                )
                
        return RedirectResponse(url="/books", status_code=302)
        
    except Exception as e:
        logging.error(f"Error deleting book: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/")
async def root(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login")
    return RedirectResponse(url="/books")

@router.get("/logs")
async def logs_page(
    request: Request, 
    page: int = 1,
    admin_id: str = "",
    action_type: str = "",
    date_from: str = "",
    date_to: str = ""
):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    items_per_page = 12
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем список админов
            cursor.execute("""
                SELECT DISTINCT u.id, u.full_name, u.username
                FROM admin_logs al
                JOIN users u ON al.admin_id = u.id
                ORDER BY COALESCE(u.full_name, u.username)
            """)
            
            admins = [{'id': row[0], 'name': row[1] or f"@{row[2]}"} for row in cursor.fetchall()]
            
            # Базовый запрос
            query = """
                SELECT 
                    al.id,
                    al.action_type,
                    al.details,
                    strftime('%d.%m.%Y %H:%M', al.timestamp) as formatted_time,
                    u.full_name,
                    u.username
                FROM admin_logs al
                JOIN users u ON al.admin_id = u.id
                WHERE 1=1
            """
            params = []
            
            # Добавляем фильтры
            if admin_id:
                query += " AND al.admin_id = ?"
                params.append(admin_id)
            
            if action_type:
                query += " AND al.action_type = ?"
                params.append(action_type)
                
            if date_from:
                try:
                    # Конвертируем дату из dd.mm.yyyy в yyyy-mm-dd
                    day, month, year = date_from.split('.')
                    formatted_date = f"{year}-{month}-{day}"
                    query += " AND date(al.timestamp) >= date(?)"
                    params.append(formatted_date)
                except:
                    pass
                
            if date_to:
                try:
                    # Конвертируем дату из dd.mm.yyyy в yyyy-mm-dd
                    day, month, year = date_to.split('.')
                    formatted_date = f"{year}-{month}-{day}"
                    query += " AND date(al.timestamp) <= date(?)"
                    params.append(formatted_date)
                except:
                    pass
            
            # Получаем общее количество записей
            count_query = f"SELECT COUNT(*) FROM ({query})"
            cursor.execute(count_query, params)
            total_records = cursor.fetchone()[0]
            
            # Вычисляем пагинацию
            total_pages = (total_records + items_per_page - 1) // items_per_page
            
            # Проверяем, что page находится в допустимом диапазоне
            page = max(1, min(page, total_pages)) if total_pages > 0 else 1
            offset = (page - 1) * items_per_page
            
            # Добавляем сортировку и лимиты
            query += " ORDER BY al.timestamp DESC LIMIT ? OFFSET ?"
            params.extend([items_per_page, offset])
            
            # Получаем записи
            cursor.execute(query, params)
            
            logs = []
            for row in cursor.fetchall():
                logs.append({
                    'id': row[0],
                    'action_type': row[1],
                    'details': row[2],
                    'timestamp': row[3],
                    'admin_name': row[4] or f"@{row[5]}"
                })
            
            # Формируем строку фильтров для пагинации
            filter_parts = []
            if admin_id:
                filter_parts.append(f"admin_id={admin_id}")
            if action_type:
                filter_parts.append(f"action_type={action_type}")
            if date_from:
                filter_parts.append(f"date_from={date_from}")
            if date_to:
                filter_parts.append(f"date_to={date_to}")
            filter_query = "&".join(filter_parts)
                
            return templates.TemplateResponse(
                "logs.html",
                {
                    "request": request,
                    "logs": logs,
                    "admin_info": admin_info,
                    "current_page": page,
                    "total_pages": total_pages,
                    "filter_query": filter_query,
                    "filters": {
                        "admin_id": admin_id,
                        "action_type": action_type,
                        "date_from": date_from,
                        "date_to": date_to
                    },
                    "admins": admins
                }
            )
    except Exception as e:
        logging.error(f"Error loading logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/login")
async def login_page(request: Request):
    token = request.query_params.get('token')
    
    if token:
        # Проверяем токен
        user_id = verify_token(token)
        if user_id:
            # Если токен валидный, сохраняем данные в сессию
            request.session['user_id'] = user_id
            request.session['is_admin'] = True
            
            # Перенаправляем на главную страницу
            return RedirectResponse(url="/books")
            
    # Если нет токена или токен невалидный, показываем ошибку
    return templates.TemplateResponse(
        "error.html",
        {
            "request": request,
            "message": "Недействительная или истекшая ссылка. Пожалуйста, получите новую ссылку через бота."
        }
    )

@router.get("/books")
async def list_books(
    request: Request,
    search: str = Query(None),
    page: int = Query(1, ge=1)
):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    items_per_page = 10  # Количество книг на странице
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Базовый запрос для поиска
            search_query = f"%{search}%" if search else "%"
            
            # Получаем общее количество книг и статистику
            cursor.execute("""
                SELECT 
                    COUNT(DISTINCT b.id) as total_books,
                    COUNT(DISTINCT bc.id) as total_copies,
                    COUNT(CASE WHEN bb.status = 'borrowed' THEN 1 END) as borrowed_copies
                FROM books b
                LEFT JOIN book_copies bc ON b.id = bc.book_id
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id
                WHERE b.title LIKE ? OR b.author LIKE ?
            """, (search_query, search_query))
            
            stats = cursor.fetchone()
            total_books = stats[0]
            total_copies = stats[1] or 0
            borrowed_copies = stats[2] or 0
            
            # Вычисляем пагинацию
            total_pages = (total_books + items_per_page - 1) // items_per_page
            offset = (page - 1) * items_per_page
            
            # Получаем книги для текущей страницы
            cursor.execute("""
                SELECT 
                    b.id,
                    b.title,
                    b.author,
                    b.description,
                    b.theme,
                    b.pages,
                    b.edition_number,
                    b.publication_year,
                    b.publisher,
                    COUNT(DISTINCT bc.id) as total_copies,
                    COUNT(CASE WHEN bb.status = 'borrowed' THEN 1 END) as borrowed_copies,
                    ROUND(AVG(COALESCE(bp.price_per_unit, 0)), 2) as avg_price
                FROM books b
                LEFT JOIN book_copies bc ON b.id = bc.book_id
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id
                LEFT JOIN book_purchases bp ON b.id = bp.book_id
                WHERE b.title LIKE ? OR b.author LIKE ?
                GROUP BY b.id
                ORDER BY b.title
                LIMIT ? OFFSET ?
            """, (search_query, search_query, items_per_page, offset))
            
            books = []
            for row in cursor.fetchall():
                books.append({
                    'id': row[0],
                    'title': row[1],
                    'author': row[2],
                    'description': row[3],
                    'theme': row[4],
                    'pages': row[5],
                    'edition_number': row[6],
                    'publication_year': row[7],
                    'publisher': row[8],
                    'total_copies': row[9],
                    'available_copies': row[9] - row[10] if row[9] and row[10] is not None else 0,
                    'avg_price': row[11]
                })
                
            return templates.TemplateResponse(
                "books.html",
                {
                    "request": request,
                    "books": books,
                    "admin_info": admin_info,
                    "total_books": total_books,
                    "total_copies": total_copies,
                    "borrowed_copies": borrowed_copies,
                    "current_page": page,
                    "total_pages": total_pages,
                    "search_query": search
                }
            )
    except Exception as e:
        logging.error(f"Error loading books page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/suggestions")
async def suggestions_page(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login")
    
    admin_info = get_admin_info(request)
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    bs.id,
                    bs.title,
                    bs.url,
                    bs.price,
                    bs.reason,
                    bs.status,
                    bs.created_at,
                    u.full_name,
                    u.username
                FROM book_suggestions bs
                JOIN users u ON bs.user_id = u.id
                ORDER BY bs.created_at DESC
            """)
            
            suggestions = []
            for row in cursor.fetchall():
                suggestions.append({
                    'id': row[0],
                    'title': row[1],
                    'url': row[2],
                    'price': row[3],
                    'reason': row[4],
                    'status': row[5],
                    'created_at': row[6],
                    'user_name': row[7] or f"@{row[8]}"
                })
                
            return templates.TemplateResponse(
                "suggestions.html",
                {
                    "request": request, 
                    "suggestions": suggestions,
                    "admin_info": admin_info
                }
            )
    except Exception as e:
        logging.error(f"Error loading suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/suggestions/{suggestion_id}/status")
async def update_suggestion_status(suggestion_id: int, request: Request):
    if not is_admin(request):
        return JSONResponse({"success": False, "error": "Unauthorized"})
        
    try:
        data = await request.json()
        new_status = data.get('status')
        
        if new_status not in ['approved', 'rejected']:
            return JSONResponse({"success": False, "error": "Invalid status"})
            
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE book_suggestions 
                SET status = ? 
                WHERE id = ?
            """, (new_status, suggestion_id))
            conn.commit()
            
        return JSONResponse({"success": True})
        
    except Exception as e:
        logging.error(f"Error updating suggestion status: {e}")
        return JSONResponse({"success": False, "error": str(e)})

@router.get("/books/{book_id}/qrcodes")
async def book_qrcodes(request: Request, book_id: int):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем информацию о книге
            cursor.execute("SELECT title, author FROM books WHERE id = ?", (book_id,))
            book = cursor.fetchone()
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")
                
            # Получаем QR коды книги с правильным статусом
            cursor.execute("""
                SELECT 
                    bc.id, 
                    CASE 
                        WHEN bb.status = 'borrowed' THEN 'borrowed'
                        WHEN bc.status = 'written_off' THEN 'written_off'
                        ELSE 'available'
                    END as status,
                    bb.user_id,
                    u.full_name,
                    u.username
                FROM book_copies bc
                LEFT JOIN borrowed_books bb ON bc.id = bb.copy_id 
                    AND bb.status = 'borrowed'
                LEFT JOIN users u ON bb.user_id = u.id
                WHERE bc.book_id = ?
                ORDER BY bc.id
            """, (book_id,))
            
            copies = []
            for row in cursor.fetchall():
                copy_id, status, user_id, full_name, username = row
                copies.append({
                    'id': copy_id,
                    'status': status,
                    'borrowed_by': full_name or f"@{username}" if user_id else None
                })
                
            return templates.TemplateResponse(
                "book_qrcodes.html",
                {
                    "request": request,
                    "book": {
                        'id': book_id,
                        'title': book[0],
                        'author': book[1]
                    },
                    "copies": copies,
                    "admin_info": admin_info
                }
            )
    except Exception as e:
        logging.error(f"Error loading QR codes: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/books/{book_id}/purchases")
async def get_book_purchases(request: Request, book_id: int):
    if not is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    strftime('%d.%m.%Y', purchase_date) as formatted_date,
                    quantity,
                    price_per_unit,
                    supplier
                FROM book_purchases
                WHERE book_id = ?
                ORDER BY purchase_date DESC
            """, (book_id,))
            
            purchases = []
            for row in cursor.fetchall():
                purchases.append({
                    'date': row[0],
                    'quantity': row[1],
                    'price': row[2],
                    'supplier': row[3]
                })
                
            return JSONResponse({"purchases": purchases})
    except Exception as e:
        logging.error(f"Error getting purchases: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/books/{book_id}/purchases/add")
async def add_book_purchase(request: Request, book_id: int):
    if not is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    try:
        data = await request.json()
        quantity = data.get('quantity')
        price = data.get('price')
        supplier = data.get('supplier')
        admin_id = request.session.get('user_id')
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Начинаем транзакцию
            cursor.execute("BEGIN")
            
            try:
                # Получаем информацию о книге
                cursor.execute("SELECT title FROM books WHERE id = ?", (book_id,))
                book = cursor.fetchone()
                if not book:
                    return JSONResponse({"error": "Книга не найдена"}, status_code=404)
                
                book_title = book[0]
                
                # Добавляем запись о закупке с текущей датой
                cursor.execute("""
                    INSERT INTO book_purchases (book_id, quantity, price_per_unit, supplier, purchase_date)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                """, (book_id, quantity, price, supplier))
                
                # Получаем текущее количество копий для этой книги
                cursor.execute("SELECT COUNT(*) FROM book_copies WHERE book_id = ?", (book_id,))
                current_copies = cursor.fetchone()[0]
                
                # Создаем новые копии книги
                for i in range(quantity):
                    copy_number = current_copies + i + 1
                    cursor.execute("""
                        INSERT INTO book_copies (book_id, copy_number, status)
                        VALUES (?, ?, 'available')
                    """, (book_id, copy_number))
                
                # Обновляем количество книг
                cursor.execute("""
                    UPDATE books 
                    SET quantity = quantity + ?
                    WHERE id = ?
                """, (quantity, book_id))
                
                # Логируем действие в той же транзакции
                cursor.execute("""
                    INSERT INTO admin_logs (admin_id, action_type, book_id, details, timestamp)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                """, (
                    admin_id,
                    "add_purchase",
                    book_id,
                    f"Добавлена закупка книги '{book_title}': {quantity} шт. по {price} ₽ от {supplier}"
                ))
                
                # Завершаем транзакцию
                conn.commit()
                return JSONResponse({"success": True})
                
            except Exception as e:
                # В случае ошибки откатываем изменения
                cursor.execute("ROLLBACK")
                raise e
            
    except Exception as e:
        logging.error(f"Error adding purchase: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/qr/{copy_id}")
async def get_qr_code(copy_id: int):
    # Генерируем QR код
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(str(copy_id))
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Сохраняем в буфер
    buf = BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    
    return StreamingResponse(buf, media_type="image/png")

@router.post("/books/copies/{copy_id}/write-off")
async def write_off_copy(request: Request, copy_id: int):
    if not is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Начинаем транзакцию
            cursor.execute("BEGIN")
            
            try:
                # Проверяем существование и статус копии
                cursor.execute("""
                    SELECT bc.id, b.title, b.id 
                    FROM book_copies bc
                    JOIN books b ON bc.book_id = b.id
                    WHERE bc.id = ? AND bc.status = 'available'
                """, (copy_id,))
                
                result = cursor.fetchone()
                if not result:
                    return JSONResponse(
                        {"error": "Копия не найдена или уже выдана"}, 
                        status_code=404
                    )
                
                book_id = result[2]
                
                # Списываем копию
                cursor.execute("""
                    UPDATE book_copies 
                    SET status = 'written_off' 
                    WHERE id = ?
                """, (copy_id,))
                
                # Уменьшаем количество книг
                cursor.execute("""
                    UPDATE books 
                    SET quantity = quantity - 1
                    WHERE id = ?
                """, (book_id,))
                
                # Добавляем запись в лог
                admin_id = request.session.get('user_id')
                cursor.execute("""
                    INSERT INTO admin_logs (admin_id, action_type, book_id, details, timestamp)
                    VALUES (?, ?, ?, ?, datetime('now', 'localtime'))
                """, (admin_id, "write_off_copy", book_id, f"Списан экземпляр #{copy_id} книги '{result[1]}'"))
                
                # Завершаем транзакцию
                conn.commit()
                return JSONResponse({"success": True})
                
            except Exception as e:
                # Если произошла ошибка, откатываем изменения
                cursor.execute("ROLLBACK")
                raise e
            
    except Exception as e:
        logging.error(f"Error writing off copy: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.post("/api/books")
async def create_book(request: Request):
    if not is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        data = await request.json()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO books (title, author, description, theme, quantity)
                VALUES (?, ?, ?, ?, 0)
            """, (data['title'], data['author'], data['description'], data['theme']))
            conn.commit()
        return JSONResponse({"success": True})
    except Exception as e:
        logging.error(f"Error creating book: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.put("/books/{book_id}/edit")
async def edit_book(
    request: Request,
    book_id: int,
    title: str = Form(...),
    author: str = Form(...),
    theme: str = Form(...),
    description: str = Form(...),
    pages: str = Form(...),
    edition_number: str = Form(None),
    publication_year: str = Form(...),
    publisher: str = Form(...),
    quantity: int = Form(...)
):
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем старые значения для лога
            cursor.execute("SELECT title, author FROM books WHERE id = ?", (book_id,))
            old_book = cursor.fetchone()
            old_title, old_author = old_book
            
            cursor.execute("""
                UPDATE books 
                SET title = ?, author = ?, theme = ?, description = ?,
                    pages = ?, edition_number = ?, publication_year = ?, publisher = ?, quantity = ?
                WHERE id = ?
            """, (
                title, author, theme, description,
                int(pages), edition_number, int(publication_year), publisher, quantity,
                book_id
            ))
            
            # Фиксируем изменения
            conn.commit()
            
            # Логируем действие
            admin_id = request.session.get('user_id')
            log_admin_action(
                admin_id=admin_id,
                action_type="edit_book",
                book_id=book_id,
                details=f"Изменена книга: '{old_title}' -> '{title}', '{old_author}' -> '{author}'"
            )
        
        return RedirectResponse(url="/books", status_code=303)
    except Exception as e:
        logging.error(f"Error editing book: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users")
async def users_page(request: Request, page: int = 1, search: str = ""):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    items_per_page = 12
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Базовый запрос для поиска
            search_query = f"%{search}%" if search else "%"
            
            # Получаем статистику пользователей
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_users,
                    SUM(CASE WHEN role = 'admin' THEN 1 ELSE 0 END) as admin_count,
                    SUM(CASE WHEN role = 'teacher' THEN 1 ELSE 0 END) as teacher_count,
                    SUM(CASE WHEN role = 'user' OR role IS NULL OR role = '' THEN 1 ELSE 0 END) as user_count
                FROM users
            """)
            stats = cursor.fetchone()
            
            # Получаем общее количество пользователей для пагинации
            count_query = """
                SELECT COUNT(*)
                FROM users u
                WHERE 1=1
            """
            params = []
            
            if search:
                count_query += """ 
                    AND (
                        u.username LIKE ? OR 
                        u.full_name LIKE ? OR 
                        u.phone LIKE ? OR
                        CAST(u.id AS TEXT) LIKE ?
                    )
                """
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            cursor.execute(count_query, params)
            total_records = cursor.fetchone()[0]
            
            # Вычисляем пагинацию
            total_pages = (total_records + items_per_page - 1) // items_per_page
            page = max(1, min(page, total_pages)) if total_pages > 0 else 1
            offset = (page - 1) * items_per_page
            
            # Базовый запрос с форматированием даты и времени
            query = """
                SELECT 
                    u.id,
                    u.username,
                    u.full_name,
                    u.phone,
                    u.role,
                    COUNT(DISTINCT CASE WHEN bb.status = 'borrowed' THEN bb.id END) as active_borrows,
                    COUNT(DISTINCT CASE WHEN br.id IS NOT NULL THEN br.id END) as review_count,
                    strftime('%d.%m.%Y %H:%M', MAX(bb.borrow_date)) as last_activity,
                    u.is_blocked
                FROM users u
                LEFT JOIN borrowed_books bb ON u.id = bb.user_id
                LEFT JOIN book_reviews br ON u.id = br.user_id
                WHERE 1=1
            """
            params = []
            
            # Добавляем условия поиска
            if search:
                query += """ 
                    AND (
                        u.username LIKE ? OR 
                        u.full_name LIKE ? OR 
                        u.phone LIKE ? OR
                        CAST(u.id AS TEXT) LIKE ?
                    )
                """
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            # Добавляем группировку и сортировку
            query += """
                GROUP BY u.id, u.username, u.full_name, u.phone, u.role, u.is_blocked
                ORDER BY u.id DESC
                LIMIT ? OFFSET ?
            """
            params.extend([items_per_page, offset])
            
            cursor.execute(query, params)
            users = cursor.fetchall()
            
            return templates.TemplateResponse(
                "users.html",
                {
                    "request": request,
                    "admin_info": admin_info,
                    "stats": stats,
                    "users": users,
                    "filters": {
                        "search": search,
                        "role": "",
                        "status": ""
                    },
                    "current_page": page,
                    "total_pages": total_pages,
                    "filter_query": "",
                    "max": max,
                    "min": min
                }
            )
            
    except Exception as e:
        logging.error(f"Error loading users: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/users/{user_id}/toggle_block")
async def toggle_user_block(request: Request, user_id: int, reason: str = Form(...)):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем текущий статус блокировки
            cursor.execute("SELECT is_blocked FROM users WHERE id = ?", (user_id,))
            result = cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Пользователь не найден")
                
            current_status = result[0]
            new_status = 0 if current_status == 1 else 1
            
            # Обновляем статус
            cursor.execute("""
                UPDATE users 
                SET is_blocked = ?
                WHERE id = ?
            """, (new_status, user_id))
            
            conn.commit()
            
            # Логируем действие
            admin_id = request.session.get('user_id')
            action = "unblock_user" if new_status == 0 else "block_user"
            log_admin_action(
                admin_id=admin_id,
                action_type=action,
                details=f"{'Разблокирован' if new_status == 0 else 'Заблокирован'} пользователь {user_id}. Причина: {reason}"
            )
            
        return RedirectResponse(url="/users", status_code=302)
        
    except Exception as e:
        logging.error(f"Error toggling user block: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/reviews")
async def reviews_page(request: Request, search: str = "", rating: str = "", status: str = ""):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем статистику отзывов
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_reviews,
                    SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as positive_reviews,
                    SUM(CASE WHEN rating <= 2 THEN 1 ELSE 0 END) as negative_reviews
                FROM book_reviews
            """)
            stats = cursor.fetchone()
            
            # Базовый запрос для отзывов
            query = """
                SELECT 
                    br.id,
                    br.rating,
                    br.review_text,
                    br.status,
                    strftime('%d.%m.%Y %H:%M', br.created_at) as created_at,
                    u.username,
                    u.full_name,
                    b.title as book_title
                FROM book_reviews br
                JOIN users u ON br.user_id = u.id
                JOIN books b ON br.book_id = b.id
                WHERE 1=1
            """
            params = []
            
            # Добавляем условия поиска
            if search:
                query += """ 
                    AND (
                        u.username LIKE ? OR 
                        u.full_name LIKE ? OR 
                        b.title LIKE ? OR
                        br.review_text LIKE ?
                    )
                """
                search_param = f"%{search}%"
                params.extend([search_param, search_param, search_param, search_param])
            
            # Фильтр по рейтингу
            if rating:
                if rating == 'positive':
                    query += " AND br.rating >= 4"
                elif rating == 'negative':
                    query += " AND br.rating <= 2"
                elif rating == 'neutral':
                    query += " AND br.rating = 3"
            
            # Фильтр по статусу
            if status:
                query += " AND br.status = ?"
                params.append(status)
            
            # Добавляем сортировку
            query += " ORDER BY br.created_at DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()  # Получаем результаты один раз
            
            # Преобразуем результаты в словари
            formatted_reviews = []
            for row in rows:  # Используем полученные ранее результаты
                formatted_reviews.append({
                    'id': row[0],
                    'rating': row[1],
                    'review_text': row[2],
                    'status': row[3],
                    'created_at': row[4],
                    'username': row[5],
                    'full_name': row[6],
                    'book_title': row[7]
                })
            
            return templates.TemplateResponse(
                "reviews.html",
                {
                    "request": request,
                    "admin_info": admin_info,
                    "stats": stats,
                    "reviews": formatted_reviews,
                    "filters": {
                        "search": search,
                        "rating": rating,
                        "status": status
                    }
                }
            )
            
    except Exception as e:
        logging.error(f"Error loading reviews: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/reviews/{review_id}/{action}")
async def handle_review(request: Request, review_id: int, action: str):
    if not is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
        
    if action not in ['approve', 'reject']:
        return JSONResponse({"error": "Invalid action"}, status_code=400)
        
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Обновляем статус отзыва
            cursor.execute("""
                UPDATE book_reviews 
                SET status = ?
                WHERE id = ?
            """, (action + 'd', review_id))  # approved или rejected
            
            conn.commit()
            
            return JSONResponse({"success": True})
            
    except Exception as e:
        logging.error(f"Error handling review: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/books/{book_id}/qrcodes")
async def book_qrcodes_page(request: Request, book_id: int):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Получаем информацию о книге
            cursor.execute("""
                SELECT id, title, author 
                FROM books
                WHERE id = ?
            """, (book_id,))
            book = cursor.fetchone()
            
            if not book:
                raise HTTPException(status_code=404, detail="Книга не найдена")
                
            book_info = {
                "id": book[0],
                "title": book[1],
                "author": book[2]
            }
            
            # Получаем все экземпляры книги
            cursor.execute("""
                SELECT id, copy_number, status
                FROM book_copies
                WHERE book_id = ?
                ORDER BY copy_number
            """, (book_id,))
            
            copies = []
            for row in cursor.fetchall():
                copies.append({
                    "id": row[0],
                    "copy_number": row[1],
                    "status": row[2]
                })
            
            return templates.TemplateResponse(
                "book_qrcodes.html",
                {
                    "request": request,
                    "admin_info": admin_info,
                    "book": book_info,
                    "copies": copies
                }
            )
    except Exception as e:
        logging.error(f"Error loading book QR codes page: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/books/template/download")
async def download_books_template(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login")
    
    # Создаем Excel файл
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Книги"
    
    # Определяем заголовки
    headers = [
        "Название книги*", "Автор*", "Тематика(Жанр)*", "Описание*",
        "Кол-во страниц*", "Номер издания (если есть)", "Год издания*", "Издательство*",
        "Дата поставки*", "Количество экземпляров*", "Цена за экземпляр*", "Поставщик*"
    ]
    
    # Заполняем заголовки
    for col_num, header in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        cell = ws[f"{col_letter}1"]
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[col_letter].width = 20
    
    # Добавляем пример данных
    example_data = [
        "Война и мир", "Лев Толстой", "Классика", "Роман-эпопея о событиях 1812 года",
        "1300", "1", "1869", "Русский вестник", 
        datetime.now().strftime("%d.%m.%Y"), "30", "1000", "Книжный дом"
    ]
    
    for col_num, value in enumerate(example_data, 1):
        ws[f"{get_column_letter(col_num)}2"] = value
    
    # Сохраняем в буфер
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    # Возвращаем файл
    return StreamingResponse(
        buffer, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=books_template.xlsx"}
    )

@router.post("/admin/books/upload")
async def upload_books_excel(request: Request):
    if not is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        # Получаем файл из запроса
        form = await request.form()
        file = form.get("file")
        if not file:
            return JSONResponse({"error": "Файл не найден"}, status_code=400)
        
        # Читаем Excel файл
        contents = await file.read()
        wb = openpyxl.load_workbook(BytesIO(contents), data_only=True)
        ws = wb.active
        
        # Проверяем заголовки
        headers = [cell.value for cell in next(ws.rows)]
        required_headers = ["Название книги*", "Автор*", "Тематика(Жанр)*", "Описание*", 
                          "Кол-во страниц*", "Год издания*", "Издательство*"]
        
        for header in required_headers:
            if header not in headers:
                return JSONResponse({"error": f"Отсутствует обязательный столбец: {header}"}, status_code=400)
        
        # Индексы столбцов
        title_idx = headers.index("Название книги*")
        author_idx = headers.index("Автор*")
        theme_idx = headers.index("Тематика(Жанр)*")
        desc_idx = headers.index("Описание*")
        pages_idx = headers.index("Кол-во страниц*")
        edition_idx = headers.index("Номер издания (если есть)") if "Номер издания (если есть)" in headers else None
        year_idx = headers.index("Год издания*")
        publisher_idx = headers.index("Издательство*")
        date_idx = headers.index("Дата поставки*")
        quantity_idx = headers.index("Количество экземпляров*")
        price_idx = headers.index("Цена за экземпляр*")
        supplier_idx = headers.index("Поставщик*")
        
        with get_db() as conn:
            cursor = conn.cursor()
            added_count = 0
            
            # Начиная со второй строки (после заголовков)
            for i, row in enumerate(list(ws.rows)[1:], 2):
                if all(cell.value is None for cell in row):
                    continue  # Пропускаем пустые строки
                
                try:
                    # Извлекаем данные
                    title = row[title_idx].value
                    author = row[author_idx].value
                    theme = row[theme_idx].value
                    description = row[desc_idx].value
                    pages = int(row[pages_idx].value or 0)
                    edition_number = row[edition_idx].value if edition_idx is not None else None
                    publication_year = int(row[year_idx].value or 0)
                    publisher = row[publisher_idx].value
                    quantity = int(row[quantity_idx].value or 0)
                    price = int(row[price_idx].value or 0)
                    supplier = row[supplier_idx].value
                    
                    # Проверяем обязательные поля
                    if not (title and author and theme and description and pages and publication_year and publisher and quantity):
                        continue
                    
                    # Добавляем книгу
                    cursor.execute("""
                        INSERT INTO books (
                            title, author, theme, description, 
                            pages, edition_number, publication_year, publisher, quantity
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        title, author, theme, description,
                        pages, edition_number, publication_year, publisher, quantity
                    ))
                    
                    book_id = cursor.lastrowid
                    
                    # Добавляем закупку
                    date_str = row[date_idx].value
                    if isinstance(date_str, datetime):
                        date_str = date_str.strftime("%Y-%m-%d")
                    elif isinstance(date_str, str):
                        # Преобразуем строку даты в формате ДД.ММ.ГГГГ в ГГГГ-ММ-ДД
                        try:
                            if '.' in date_str:
                                day, month, year = date_str.split('.')
                                date_str = f"{year}-{month}-{day}"
                        except:
                            # Если не удалось преобразовать, оставляем как есть
                            pass
                    
                    cursor.execute("""
                        INSERT INTO book_purchases (
                            book_id, purchase_date, quantity, price_per_unit, supplier
                        )
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        book_id, date_str, quantity, price, supplier
                    ))
                    
                    # Создаем записи для копий книг
                    for copy_number in range(1, quantity + 1):
                        cursor.execute("""
                            INSERT INTO book_copies (book_id, copy_number, status)
                            VALUES (?, ?, 'available')
                        """, (book_id, copy_number))
                    
                    # Фиксируем изменения
                    conn.commit()
                    added_count += 1
                    
                except Exception as e:
                    logging.error(f"Error processing row {i}: {e}")
            
            return JSONResponse({"success": True, "added": added_count})
        
    except Exception as e:
        logging.error(f"Error uploading Excel file: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@router.get("/admin/users/template/download")
async def download_users_template(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login")
    
    # Создаем Excel файл
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Пользователи"
    
    # Определяем заголовки
    headers = [
        "id_пользователя*", "Имя пользователя", "ФИО*", "Телефон*", "Роль*", "Класс"
    ]
    
    # Форматирование и заполнение шаблона
    for col_num, header in enumerate(headers, 1):
        col_letter = get_column_letter(col_num)
        cell = ws[f"{col_letter}1"]
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[col_letter].width = 20
    
    # Добавляем пример данных
    example_data = [
        "1234567890", "ivanov", "Иванов Иван Иванович", "+7 999 123 4567", "user", "9А"
    ]
    
    for col_num, value in enumerate(example_data, 1):
        ws[f"{get_column_letter(col_num)}2"] = value
    
    # Сохраняем в буфер
    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    
    # Возвращаем файл
    return StreamingResponse(
        buffer, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=users_template.xlsx"}
    )

@router.post("/admin/users/upload")
async def upload_users_excel(request: Request):
    if not is_admin(request):
        return JSONResponse({"error": "Unauthorized"}, status_code=401)
    
    try:
        # Получаем файл из запроса
        form = await request.form()
        file = form.get("file")
        if not file:
            return JSONResponse({"error": "Файл не найден"}, status_code=400)
        
        # Читаем Excel файл
        contents = await file.read()
        wb = openpyxl.load_workbook(BytesIO(contents), data_only=True)
        ws = wb.active
        
        # Проверяем заголовки
        headers = [cell.value for cell in next(ws.rows)]
        required_headers = ["id_пользователя*", "ФИО*", "Телефон*", "Роль*"]
        
        for header in required_headers:
            if header not in headers:
                return JSONResponse({"error": f"Отсутствует обязательный столбец: {header}"}, status_code=400)
        
        # Индексы столбцов
        id_idx = headers.index("id_пользователя*")
        username_idx = headers.index("Имя пользователя") if "Имя пользователя" in headers else None
        name_idx = headers.index("ФИО*")
        role_idx = headers.index("Роль*")
        class_idx = headers.index("Класс") if "Класс" in headers else None
        phone_idx = headers.index("Телефон*")
        
        with get_db() as conn:
            cursor = conn.cursor()
            added_count = 0
            
            # Начиная со второй строки (после заголовков)
            for i, row in enumerate(list(ws.rows)[1:], 2):
                if all(cell.value is None for cell in row):
                    continue  # Пропускаем пустые строки
                
                try:
                    # Извлекаем данные
                    user_id = str(row[id_idx].value)
                    username = row[username_idx].value
                    name = row[name_idx].value
                    role = row[role_idx].value
                    class_val = row[class_idx].value if class_idx is not None else None
                    phone = row[phone_idx].value
                    
                    # Проверяем обязательные поля
                    if not (user_id and username and name and role and phone):
                        continue
                        
                    # Проверяем правильность роли
                    if role not in ['admin', 'teacher', 'user']:
                        role = 'user'  # Установка роли по умолчанию
                    
                    # Проверяем существует ли пользователь
                    cursor.execute("SELECT id FROM users WHERE id = ?", (user_id,))
                    existing_user = cursor.fetchone()
                    
                    if existing_user:
                        # Обновляем существующего пользователя
                        cursor.execute("""
                            UPDATE users 
                            SET full_name = ?, role = ?, class = ?, phone = ?, username = ?
                            WHERE id = ?
                        """, (name, role, class_val, phone, username, user_id))
                    else:
                        # Добавляем нового пользователя
                        cursor.execute("""
                            INSERT INTO users (id, username, full_name, role, class, phone)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (user_id, username, name, role, class_val, phone))
                    
                    # Фиксируем изменения
                    conn.commit()
                    added_count += 1
                    
                except Exception as e:
                    logging.error(f"Error processing row {i}: {e}")
            
            return JSONResponse({"success": True, "added": added_count})
        
    except Exception as e:
        logging.error(f"Error uploading Excel file: {e}")
        return JSONResponse({"error": str(e)}, status_code=500) 