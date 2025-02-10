from fastapi import APIRouter, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from database.models import get_db, log_admin_action
from starlette.middleware.sessions import SessionMiddleware
import logging

router = APIRouter()
templates = Jinja2Templates(directory="admin_panel/templates")

def is_admin(request: Request) -> bool:
    return request.session.get('is_admin', False)

def get_admin_info(request: Request) -> dict:
    return {
        'username': request.session.get('username', 'Admin'),
        'user_id': request.session.get('user_id')
    }

# Остальные маршруты остаются теми же... 

@router.get("/suggestions")
async def suggestions_page(
    request: Request,
    status: str = Query(default=None),
    date_from: str = Query(default=None),
    date_to: str = Query(default=None)
):
    if not is_admin(request):
        return RedirectResponse(url="/login")
    
    admin_info = get_admin_info(request)
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        query = """
            SELECT 
                bs.id,
                bs.title,
                bs.url,
                bs.price,
                bs.reason,
                bs.status,
                strftime('%d.%m.%Y', bs.created_at) as created_at,
                u.full_name,
                u.username
            FROM book_suggestions bs
            JOIN users u ON bs.user_id = u.id
            WHERE 1=1
        """
        params = []

        # Добавляем отладочные логи
        logging.debug(f"Status: {status}, date_from: {date_from}, date_to: {date_to}")
        
        if status and status != 'all':
            query += " AND bs.status = ?"
            params.append(status)
            logging.debug(f"Added status filter: {status}")
            
        if date_from:
            query += " AND date(bs.created_at) >= date(?)"
            params.append(date_from)
            logging.debug(f"Added date_from filter: {date_from}")
            
        if date_to:
            query += " AND date(bs.created_at) <= date(?)"
            params.append(date_to)
            logging.debug(f"Added date_to filter: {date_to}")
        
        query += " ORDER BY bs.created_at DESC"
        
        logging.debug(f"Final query: {query}")
        logging.debug(f"Params: {params}")
        
        cursor.execute(query, params)
        
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
                "admin_info": admin_info,
                "status": status or '',
                "date_from": date_from or '',
                "date_to": date_to or ''
            }
        )
    finally:
        conn.close() 

@router.get("/books")
async def books_page(request: Request):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                b.id,
                b.title,
                b.author,
                b.theme,
                b.description,
                bc.id as copy_id,
                COALESCE(bb.status, bc.status) as status,
                bb.user_id,
                u.username,
                u.full_name
            FROM books b
            JOIN book_copies bc ON b.id = bc.book_id
            LEFT JOIN (
                SELECT * FROM borrowed_books 
                WHERE status IN ('borrowed', 'booked')
                AND id IN (
                    SELECT MAX(id) 
                    FROM borrowed_books 
                    GROUP BY copy_id
                )
            ) bb ON bc.id = bb.copy_id
            LEFT JOIN users u ON bb.user_id = u.id
            ORDER BY b.title
        """)
        
        books = []
        for row in cursor.fetchall():
            book = {
                'id': row[0],
                'title': row[1],
                'author': row[2],
                'theme': row[3],
                'description': row[4],
                'copy_id': row[5],
                'status': row[6],
                'user': {
                    'id': row[7],
                    'username': row[8],
                    'full_name': row[9]
                } if row[7] else None
            }
            books.append(book)
            
        return templates.TemplateResponse(
            "books.html",
            {
                "request": request,
                "books": books,
                "admin_info": admin_info
            }
        )
    finally:
        conn.close() 

@router.get("/books/{book_id}/qrcodes")
async def book_qrcodes(request: Request, book_id: int):
    if not is_admin(request):
        return RedirectResponse(url="/login")
        
    admin_info = get_admin_info(request)
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            WITH LastBookStatus AS (
                SELECT 
                    copy_id,
                    status,
                    user_id
                FROM borrowed_books
                WHERE id IN (
                    SELECT MAX(id)
                    FROM borrowed_books
                    GROUP BY copy_id
                )
            )
            SELECT 
                b.title,
                b.author,
                bc.id as copy_id,
                COALESCE(lbs.status, bc.status) as status,
                u.id as user_id,
                u.username,
                u.full_name
            FROM books b
            JOIN book_copies bc ON b.id = bc.book_id
            LEFT JOIN LastBookStatus lbs ON bc.id = lbs.copy_id
            LEFT JOIN users u ON lbs.user_id = u.id
            WHERE b.id = ?
            ORDER BY bc.id
        """, (book_id,))
        
        book_copies = []
        book_title = None
        book_author = None
        
        for row in cursor.fetchall():
            if not book_title:
                book_title = row[0]
                book_author = row[1]
                
            copy_info = {
                'id': row[2],
                'status': row[3],
                'user': {
                    'id': row[4],
                    'username': row[5],
                    'full_name': row[6]
                } if row[4] else None
            }
            book_copies.append(copy_info)
            
        return templates.TemplateResponse(
            "book_qrcodes.html",
            {
                "request": request,
                "book_id": book_id,
                "title": book_title,
                "author": book_author,
                "copies": book_copies,
                "admin_info": admin_info
            }
        )
    finally:
        conn.close() 