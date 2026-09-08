import os
import time
import html
import textwrap
import random
import requests
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai

# Carga de credenciales y configuración
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

SITE_URL = "https://cuanticopc.com.ar"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Paleta de colores dinámicos para darle dinamismo a cada publicación
ACCENT_COLORS = ["#00FF88", "#00E5FF", "#B000FF"]

def get_font(size):
    """Obtiene una tipografía vectorial escalable preinstalada en Linux."""
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf", size)
        except Exception:
            return ImageFont.load_default()

def clean_text(text):
    """Limpia caracteres especiales e inconsistencias de código HTML."""
    decoded = html.unescape(text)
    return decoded.replace('"', "'").replace("”", "'").strip()

def generate_ai_title(original_title):
    """Usa la API de Gemini para redactar un gancho comercial breve."""
    if not GEMINI_API_KEY:
        return original_title
        
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Transforma este título técnico de producto de computación en un texto comercial "
            f"atractivo y conciso para una Instagram Story (máximo 7 palabras, sin emojis, sin comillas):\n\n"
            f"Producto: {original_title}"
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        ai_text = response.text.strip().replace('"', '')
        return ai_text if len(ai_text) > 3 else original_title
    except Exception as e:
        print(f"Fallback a título original por error en IA: {e}")
        return original_title

def fetch_all_valid_products():
    """Obtiene todos los productos validando de forma estricta stock y precio directo sin caché."""
    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache"
    }
    
    valid_products = []
    page = 1
    
    while True:
        params = {
            "per_page": 50,
            "page": page,
            "_nocache": int(time.time())
        }
        
        res = requests.get(endpoint, params=params, headers=headers, timeout=15)
        if res.status_code != 200 or not res.json():
            break
            
        items = res.json()
        if not items:
            break
            
        for product in items:
            images = product.get("images", [])
            if not images:
                continue
            
            # Verificación de stock
            stock_status = product.get("stock_status", "")
            is_in_stock = product.get("is_in_stock", True)
            if stock_status == "outofstock" or not is_in_stock:
                continue

            prices_info = product.get("prices", {})
            raw_price = prices_info.get("price")
            
            # Filtrar si no hay precio cargado
            if raw_price is None or str(raw_price).strip() in ["", "0", "null"]:
                continue
                
            if not str(raw_price).isdigit() or int(raw_price) <= 0:
                continue
                
            val_num = int(raw_price)
            val_final = val_num / 100
            
            if val_final <= 0:
                continue

            formatted_price = f"${val_final:,.0f}".replace(",", ".")
            
            valid_products.append({
                "id": product.get("id"),
                "original_name": clean_text(product.get("name", "Producto Cuantico")),
                "price": formatted_price,
                "raw_url": images[0].get("src", "")
            })
            
        page += 1

    print(f"Se encontraron {len(valid_products)} productos con precio y stock válidos.")
    return valid_products

def draw_vertical_gradient(draw_obj, rect, color_top, color_bottom):
    """Dibuja un degradado vertical suave."""
    x1, y1, x2, y2 = rect
    height = y2 - y1
    for i in range(height):
        ratio = i / float(height)
        r = int(color_top[0] * (1 - ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1 - ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1 - ratio) + color_bottom[2] * ratio)
        a = int(color_top[3] * (1 - ratio) + color_bottom[3] * ratio)
        draw_obj.line([(x1, y1 + i), (x2, y1 + i)], fill=(r, g, b, a))

def create_story_template(product, img_obj):
    """Genera la plantilla con dinamismo en la posición del logo y paleta de color."""
    canvas_w, canvas_h = 1080, 1920
    
    # Color de acento aleatorio para esta publicación
    accent_color = random.choice(ACCENT_COLORS)
    
    # 1. Fondo difuminado
    bg = img_obj.resize((canvas_w, canvas_h)).filter(ImageFilter.GaussianBlur(50))
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (12, 12, 18, 160))
    bg.paste(overlay, (0, 0), overlay)
    
    # 2. Gradientes de sombra
    gradient_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient_layer)
    draw_vertical_gradient(g_draw, (0, 0, canvas_w, 350), (0, 0, 0, 210), (0, 0, 0, 0))
    draw_vertical_gradient(g_draw, (0, canvas_h - 350, canvas_w, canvas_h), (0, 0, 0, 0), (0, 0, 0, 230))
    bg.paste(gradient_layer, (0, 0), gradient_layer)
    
    # 3. Tarjeta para el producto
    card_w, card_h = 860, 860
    card_x = (canvas_w - card_w) // 2
    card_y = 420
    
    card_bg = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 240))
    card_mask = Image.new("L", (card_w, card_h), 0)
    card_mask_draw = ImageDraw.Draw(card_mask)
    card_mask_draw.rounded_rectangle((0, 0, card_w, card_h), radius=35, fill=255)
    
    bg.paste(card_bg, (card_x, card_y), card_mask)
    
    img_copy = img_obj.copy()
    img_copy.thumbnail((760, 760))
    p_w, p_h = img_copy.size
    p_x = card_x + (card_w - p_w) // 2
    p_y = card_y + (card_h - p_h) // 2
    bg.paste(img_copy, (p_x, p_y), img_copy if img_copy.mode == "RGBA" else None)
    
    draw = ImageDraw.Draw(bg)
    
    # 4. Render del Logo con posición aleatoria (Izquierda, Centro o Derecha)
    logo_path = os.path.join(os.path.dirname(__file__), "logo_canva.png")
    
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img.thumbnail((380, 120))
            l_w, l_h = logo_img.size
            
            # Elegir posición aleatoria
            positions = ["left", "center", "right"]
            chosen_pos = random.choice(positions)
            
            if chosen_pos == "left":
                logo_x = 70
            elif chosen_pos == "right":
                logo_x = canvas_w - l_w - 70
            else:
                logo_x = (canvas_w - l_w) // 2
                
            logo_y = 130
            # Importante: usar logo_img como máscara alfa para preservar la transparencia
            bg.paste(logo_img, (logo_x, logo_y), logo_img)
        except Exception as e:
            print(f"Error procesando el logo: {e}")
            draw.text((canvas_w // 2, 160), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")
    else:
        draw.text((canvas_w // 2, 160), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")
    
    # 5. Título del producto
    font_title = get_font(42)
    wrapped_lines = textwrap.wrap(product["ai_name"], width=22)
    wrapped_text = "\n".join(wrapped_lines[:3])
    
    title_y = card_y + card_h + 90
    draw.multiline_text(
        (canvas_w // 2, title_y), 
        wrapped_text, 
        fill="#FFFFFF", 
        font=font_title, 
        anchor="mm", 
        align="center"
    )
    
    # 6. Cápsula del precio con acento dinámico
    font_price = get_font(58)
    price_str = product["price"]
    
    bbox = draw.textbbox((0, 0), price_str, font=font_price)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    badge_padding_x = 55
    badge_padding_y = 25
    badge_w = text_w + (badge_padding_x * 2)
    badge_h = text_h + (badge_padding_y * 2)
    
    badge_x1 = (canvas_w - badge_w) // 2
    badge_y1 = title_y + 110
    badge_x2 = badge_x1 + badge_w
    badge_y2 = badge_y1 + badge_h
    
    draw.rounded_rectangle((badge_x1, badge_y1, badge_x2, badge_y2), radius=25, fill=(18, 22, 28, 240), outline=accent_color, width=3)
    draw.text(((badge_x1 + badge_x2) // 2, (badge_y1 + badge_y2) // 2 - 3), price_str, fill=accent_color, font=font_price, anchor="mm")
    
    # 7. Marca de agua inferior
    font_footer = get_font(38)
    draw.text((canvas_w // 2, canvas_h - 140), "cuanticopc.com.ar", fill="#DDDDDD", font=font_footer, anchor="mm")
    
    output_path = f"story_{product['id']}.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path

def publish_to_instagram(image_url):
    """Envía la publicación mediante la API de Meta Graph."""
    container_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "media_type": "STORIES",
        "access_token": ACCESS_TOKEN
    }
    
    res = requests.post(container_url, data=payload)
    res_data = res.json()
    
    if "id" not in res_data:
        return False, res_data
        
    container_id = res_data["id"]
    time.sleep(5)
    
    publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
    pub_payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    
    pub_res = requests.post(publish_url, data=pub_payload)
    pub_data = pub_res.json()
    
    if "id" in pub_data:
        return True, pub_data["id"]
    return False, pub_data

def process_catalog():
    """Recorre la lista de productos pidiendo aprobación interactiva en Telegram."""
    products = fetch_all_valid_products()
    if not products:
        bot.send_message(TELEGRAM_CHAT_ID, "❌ No se encontraron productos válidos para publicar.")
        return

    headers = {"User-Agent": "Mozilla/5.0"}
    total = len(products)
    
    bot.send_message(TELEGRAM_CHAT_ID, f"🚀 *Iniciando revisión de catálogo completo* ({total} productos encontrados).", parse_mode="Markdown")

    for index, prod in enumerate(products, start=1):
        try:
            img_res = requests.get(prod["raw_url"], headers=headers, timeout=10)
            if img_res.status_code != 200:
                continue
                
            img_obj = Image.open(BytesIO(img_res.content)).convert("RGB")
            
            prod["ai_name"] = generate_ai_title(prod["original_name"])
            image_path = create_story_template(prod, img_obj)
            
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Aprobar y Publicar", callback_data=f"approve_{prod['id']}"),
                InlineKeyboardButton("⏭️ Siguiente", callback_data=f"skip_{prod['id']}"),
                InlineKeyboardButton("🛑 Detener", callback_data="stop")
            )
            
            caption = (
                f"📦 *[{index}/{total}] {prod['original_name']}*\n"
                f"💰 Precio: {prod['price']}\n\n"
                f"¿Publicar esta Story?"
            )
            
            with open(image_path, "rb") as photo:
                msg = bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
                
            user_choice = {"action": None}
            
            @bot.callback_query_handler(func=lambda call: True)
            def callback_listener(call):
                if call.data.startswith("approve_"):
                    user_choice["action"] = "approve"
                    bot.answer_callback_query(call.id, "Publicando...")
                    bot.edit_message_caption(chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id, caption="🚀 *Publicando en Instagram Stories...*", parse_mode="Markdown")
                elif call.data.startswith("skip_"):
                    user_choice["action"] = "skip"
                    bot.answer_callback_query(call.id, "Salteado.")
                    bot.edit_message_caption(chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id, caption="⏭️ *Producto salteado.*", parse_mode="Markdown")
                elif call.data == "stop":
                    user_choice["action"] = "stop"
                    bot.answer_callback_query(call.id, "Deteniendo proceso...")
                    bot.edit_message_caption(chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id, caption="🛑 *Proceso detenido.*", parse_mode="Markdown")
                
                bot.stop_polling()

            bot.polling(timeout=300, non_stop=False)
            
            if os.path.exists(image_path):
                os.remove(image_path)
                
            if user_choice["action"] == "approve":
                success, result = publish_to_instagram(prod["raw_url"])
                if success:
                    bot.send_message(TELEGRAM_CHAT_ID, f"🎉 ¡Publicado exitosamente en Instagram!", parse_mode="Markdown")
                else:
                    bot.send_message(TELEGRAM_CHAT_ID, f"❌ Error al publicar en Meta: `{result}`", parse_mode="Markdown")
                time.sleep(3)
                
            elif user_choice["action"] == "stop":
                bot.send_message(TELEGRAM_CHAT_ID, "🏁 *Secuencia finalizada por el usuario.*", parse_mode="Markdown")
                break
                
        except Exception as e:
            print(f"Error procesando producto {prod['id']}: {e}")
            continue

if __name__ == "__main__":
    process_catalog()
