# utils/pdf_generator.py

import os
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from PIL import Image
import textwrap

# Папка с шрифтами (обязательно положите DejaVuSans.ttf туда)
FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

# Регистрируем шрифт DejaVuSans для кириллицы
pdfmetrics.registerFont(
    TTFont("DejaVuSans", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
)

def generate_pdf(ticket_id: str,
                 author_name: str,
                 issue_description: str,
                 messages: list,
                 attachments: list):
    """
    Генерирует PDF:
      - ticket_id: идентификатор (имя канала),
      - author_name: ник создателя тикета,
      - issue_description: исходное описание проблемы,
      - messages: список словарей {'author': str, 'content': str},
      - attachments: список кортежей (local_path, original_url).
    Для каждого вложения:
      - Если расширение .png/.jpg/.jpeg/.gif → вставляем как изображение (для GIF берётся первый кадр).
      - Если расширение видео (.mp4/.mov/.webm) → выводим кликабельную ссылку на original_url,
        а внизу помечаем "Видео сохранено локально: имя_файла".
      - Остальные файлы → просто текстом "Вложение: <original_url>".
    """
    os.makedirs("logs", exist_ok=True)
    now_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"logs/ticket_{ticket_id}_{now_str}.pdf"
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    left = 15 * mm
    right = width - 15 * mm
    y = height - 20 * mm

    # Заголовок
    c.setFont("DejaVuSans", 16)
    c.drawCentredString(width / 2, y, f"Тикет #{ticket_id}")
    y -= 10 * mm

    # Автор и описание
    c.setFont("DejaVuSans", 12)
    c.drawString(left, y, f"Автор тикета: {author_name}")
    y -= 7 * mm

    c.drawString(left, y, "Описание проблемы:")
    y -= 7 * mm

    # Описание проблемы с переносами по ~80 символов
    text_obj = c.beginText(left, y)
    text_obj.setFont("DejaVuSans", 11)
    for line in issue_description.splitlines():
        wrapped = textwrap.wrap(line, width=80)
        for part in wrapped:
            text_obj.textLine(part)
            y -= 5 * mm
    c.drawText(text_obj)
    y = text_obj.getY() - 10 * mm

    # Переписка
    c.setFont("DejaVuSans", 12)
    c.drawString(left, y, "Переписка:")
    y -= 7 * mm

    c.setFont("DejaVuSans", 10)
    for msg in messages:
        if y < 50 * mm:
            c.showPage()
            y = height - 20 * mm
            c.setFont("DejaVuSans", 10)

        author_line = f"{msg['author']}:"
        c.drawString(left, y, author_line)
        y -= 5 * mm

        wrapped = textwrap.wrap(msg["content"], width=80)
        for part in wrapped:
            if y < 50 * mm:
                c.showPage()
                y = height - 20 * mm
                c.setFont("DejaVuSans", 10)
            c.drawString(left + 10, y, part)
            y -= 5 * mm

        y -= 3 * mm

    # Вложения
    if attachments:
        if y < 60 * mm:
            c.showPage()
            y = height - 20 * mm
        c.setFont("DejaVuSans", 12)
        c.drawString(left, y, "Вложения:")
        y -= 10 * mm

        for local_path, orig_url in attachments:
            ext = os.path.splitext(local_path)[1].lower()
            # Если изображение
            if ext in (".png", ".jpg", ".jpeg", ".gif"):
                if y < 60 * mm:
                    c.showPage()
                    y = height - 20 * mm
                try:
                    img = Image.open(local_path)
                    # Если GIF — берём первый кадр
                    if ext == ".gif":
                        img = img.convert("RGBA")
                    max_w = right - left
                    max_h = 100 * mm
                    img.thumbnail((max_w, max_h), Image.ANTIALIAS)
                    img_reader = ImageReader(img)
                    iw, ih = img.size

                    if y - ih < 50 * mm:
                        c.showPage()
                        y = height - 20 * mm

                    c.drawImage(img_reader, left, y - ih, width=iw, height=ih)
                    y -= ih + 10 * mm
                except Exception:
                    c.setFont("DejaVuSans", 10)
                    c.drawString(left, y, f"❌ Ошибка вставки изображения: {os.path.basename(local_path)}")
                    y -= 7 * mm

            # Если видео
            elif ext in (".mp4", ".mov", ".webm"):
                if y < 50 * mm:
                    c.showPage()
                    y = height - 20 * mm
                c.setFont("DejaVuSans", 10)
                text = f"Видео: {orig_url}"
                wrapped = textwrap.wrap(text, width=80)
                for part in wrapped:
                    if y < 50 * mm:
                        c.showPage()
                        y = height - 20 * mm
                        c.setFont("DejaVuSans", 10)
                    c.drawString(left, y, part)
                    if orig_url in part:
                        prefix = part.split(orig_url)[0]
                        px = left + pdfmetrics.stringWidth(prefix, "DejaVuSans", 10)
                        pw = pdfmetrics.stringWidth(orig_url, "DejaVuSans", 10)
                        c.linkURL(orig_url, (px, y - 2, px + pw, y + 8), relative=0)
                    y -= 5 * mm
                c.drawString(left + 10, y, f"(Сохранено локально: {os.path.basename(local_path)})")
                y -= 10 * mm

            # Иные файлы
            else:
                if y < 50 * mm:
                    c.showPage()
                    y = height - 20 * mm
                c.setFont("DejaVuSans", 10)
                text = f"Вложение: {orig_url}"
                wrapped = textwrap.wrap(text, width=80)
                for part in wrapped:
                    if y < 50 * mm:
                        c.showPage()
                        y = height - 20 * mm
                        c.setFont("DejaVuSans", 10)
                    c.drawString(left, y, part)
                    if orig_url in part:
                        prefix = part.split(orig_url)[0]
                        px = left + pdfmetrics.stringWidth(prefix, "DejaVuSans", 10)
                        pw = pdfmetrics.stringWidth(orig_url, "DejaVuSans", 10)
                        c.linkURL(orig_url, (px, y - 2, px + pw, y + 8), relative=0)
                    y -= 5 * mm
                y -= 5 * mm

    c.save()
    return filename
