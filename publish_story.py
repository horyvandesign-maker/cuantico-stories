import os
import time
import html
import textwrap
import random
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai

# Configuración de Variables de Entorno
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

SITE_URL = "https://cuanticopc.com.ar"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

ACCENT_COLORS = ["#00FF88", "#00E5FF", "#B000FF", "#FF007F"]
HEADER_TAGS = ["NUEVO INGRESO", "OFERTA DESTACADA", "STOCK DISPONIBLE", "EQUIPO GAMER"]

def get_font(size):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/freefont/FreeSansBold.ttf", size)
        except Exception:
            return ImageFont.load_default()

def clean_text(text):
    decoded = html.unescape(text)
    return decoded.replace('"', "'").replace("”", "'").strip()

def generate_ai_title(original_title):
    if not GEMINI_API_KEY:
        return original_title
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Transforma este título técnico de producto en un texto comercial "
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
        print(f"Fallback a título original: {e}")
        return original_title

def fetch_all_valid_products():
    """Descarga el catálogo FILTRANDO estrictamente productos activos e in-stock."""
    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cache-Control": "no-cache"
    }
    valid_products = []
    page = 1
    
    while True:
        params = {"per_page": 50, "page": page, "_nocache": int(time.time())}
        res = requests.get(endpoint, params=params, headers=headers, timeout=15)
        if res.status_code != 200 or not res.json():
            break
        items = res.json()
        if not items:
            break
            
        for product in items:
            # FILTRO CRÍTICO 1: No procesar productos que no estén 'publish' (pausados, borradores, etc.)
            if product.get("status") != "publish":
                continue

            # FILTRO CRÍTICO 2: Control estricto de Stock
            if product.get("stock_status") != "instock" or not product.get("is_in_stock", True):
                continue

            images = product.get("images", [])
            if not images:
                continue

            raw_price = product.get("prices", {}).get("price")
            if not raw_price or not str(raw_price).isdigit() or int(raw_price) <= 0:
                continue
                
            val_final = int(raw_price) / 100
            formatted_price = f"${val_final:,.0f}".replace(",", ".")
            
            valid_products.append({
                "id": product.get("id"),
                "original_name": clean_text(product.get("name", "Producto Cuantico")),
                "price": formatted_price,
                "permalink": product.get("permalink", SITE_URL),
                "raw_url": images[0].get("src", "")
            })
        page += 1

    print(f"Productos activos en stock encontrados: {len(valid_products)}")
    return valid_products

def draw_vertical_gradient(draw_obj, rect, color_top, color_bottom):
    x1, y1, x2, y2 = rect
    height = y2 - y1
    for i in range(height):
        ratio = i / float(height)
        r = int(color_top[0] * (1 - ratio) + color_bottom[0] * ratio)
        g = int(color_top[1] * (1 - ratio) + color_bottom[1] * ratio)
        b = int(color_top[2] * (1 - ratio) + color_bottom[2] * ratio)
        a = int(color_top[3] * (1 - ratio) + color_bottom[3] * ratio)
        draw_obj.line([(x1, y1 + i), (x2, y1 + i)], fill=(r, g, b, a))

def create_story_template(product, img_obj, mode="STOCK"):
    canvas_w, canvas_h = 1080, 1920
    accent_color = random.choice(ACCENT_COLORS)
    
    header_text = "CONSEGUILO POR ENCARGO" if mode == "ENCARGO" else random.choice(HEADER_TAGS)
    
    bg = Image.new("RGBA", (canvas_w, canvas_h), (10, 8, 20, 255))
    g_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(g_layer)
    draw_vertical_gradient(g_draw, (0, 0, canvas_w, canvas_h), (18, 12, 38, 255), (6, 5, 15, 255))
    bg.paste(g_layer, (0, 0), g_layer)
    
    draw = ImageDraw.Draw(bg)
    
    font_header = get_font(34)
    draw.text((70, 65), header_text, fill="#00E5FF" if mode == "ENCARGO" else "#FFFFFF", font=font_header)
    
    card_w, card_h = 860, 860
    card_x, card_y = (canvas_w - card_w) // 2, 400
    
    card_bg = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 245))
    card_mask = Image.new("L", (card_w, card_h), 0)
    ImageDraw.Draw(card_mask).rounded_rectangle((0, 0, card_w, card_h), radius=35, fill=255)
    bg.paste(card_bg, (card_x, card_y), card_mask)
    
    img_copy = img_obj.copy()
    img_copy.thumbnail((760, 760))
    p_w, p_h = img_copy.size
    bg.paste(img_copy, (card_x + (card_w - p_w) // 2, card_y + (card_h - p_h) // 2), img_copy if img_copy.mode == "RGBA" else None)
    
    logo_path = os.path.join(os.path.dirname(__file__), "logo_canva.png")
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img.thumbnail((550, 220))
            bg.paste(logo_img, ((canvas_w - logo_img.width) // 2, 135), logo_img)
        except Exception:
            draw.text((canvas_w // 2, 165), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")
    else:
        draw.text((canvas_w // 2, 165), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")
    
    font_title = get_font(42)
    wrapped_lines = textwrap.wrap(product["ai_name"], width=22)
    title_y = card_y + card_h + 90
    draw.multiline_text((canvas_w // 2, title_y), "\n".join(wrapped_lines[:3]), fill="#FFFFFF", font=font_title, anchor="mm", align="center")
    
    font_price = get_font(58)
    price_str = product["price"]
    bbox = draw.textbbox((0, 0), price_str, font=font_price)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    
    badge_w, badge_h = text_w + 110, text_h + 50
    badge_x1, badge_y1 = (canvas_w - badge_w) // 2, title_y + 110
    
    draw.rounded_rectangle((badge_x1, badge_y1, badge_x1 + badge_w, badge_y1 + badge_h), radius=25, fill=(18, 22, 28, 240), outline=accent_color, width=3)
    draw.text((canvas_w // 2, badge_y1 + badge_h // 2 - 3), price_str, fill=accent_color, font=font_price, anchor="mm")
    
    footer_text = "📩 PEDILO A PEDIDO POR PRIVADO" if mode == "ENCARGO" else "🔗 COMPRÁ EN EL LINK DE LA BIO"
    draw.text((70, canvas_h - 110), footer_text, fill="#00E5FF", font=get_font(25))
    draw.text((70, canvas_h - 65), "@CUANTICOPC", fill="#FFFFFF", font=get_font(32))
    
    output_path = f"story_{product['id']}.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path

def publish_to_instagram(image_url):
    if not IG_USER_ID or not ACCESS_TOKEN:
        return False, "Faltan credenciales de Instagram"
    
    container_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
    payload = {"image_url": image_url, "media_type": "STORIES", "access_token": ACCESS_TOKEN}
    
    res = requests.post(container_url, data=payload)
    res_data = res.json()
    if "id" not in res_data:
        return False, res_data
        
    container_id = res_data["id"]
    time.sleep(5)
    
    publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
    pub_res = requests.post(publish_url, data={"creation_id": container_id, "access_token": ACCESS_TOKEN})
    pub_data = pub_res.json()
    
    if "id" in pub_data:
        return True, pub_data["id"]
    return False, pub_data

def interactive_process():
    if not bot or not TELEGRAM_CHAT_ID:
        print("Bot Token o Chat ID faltante")
        return

    products = fetch_all_valid_products()
    if not products:
        bot.send_message(TELEGRAM_CHAT_ID, "⚠️ No hay productos disponibles en stock activo.")
        return

    # Selección aleatoria de 1 producto para validar en esta corrida
    product = random.choice(products)
    
    try:
        img_res = requests.get(product["raw_url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if img_res.status_code != 200:
            return
            
        img_obj = Image.open(BytesIO(img_res.content)).convert("RGB")
        product["ai_name"] = generate_ai_title(product["original_name"])
        image_path = create_story_template(product, img_obj)
        
        # Botones interactivos
        markup = InlineKeyboardMarkup(row_width=2)
        btn_approve = InlineKeyboardButton("✅ Publicar (Stock)", callback_data=f"pub_{product['id']}")
        btn_order = InlineKeyboardButton("📦 Publicar (A Pedido)", callback_data=f"ord_{product['id']}")
        btn_skip = InlineKeyboardButton("⏩ Saltear", callback_data="skip")
        markup.add(btn_approve, btn_order, btn_skip)
        
        with open(image_path, "rb") as photo:
            msg = bot.send_photo(
                TELEGRAM_CHAT_ID, 
                photo, 
                caption=f"¿Publicar esta Story?\n\n📦 *{product['original_name']}*\n💰 {product['price']}\n🔗 [Ver en la web]({product['permalink']})", 
                parse_mode="Markdown",
                reply_markup=markup
            )
        
        # Espera activa de respuesta dentro del tiempo límite seguro
        user_action = {"done": False}

        @bot.callback_query_handler(func=lambda call: True)
        def handle_query(call):
            if call.data.startswith("pub_"):
                bot.edit_message_caption("⏳ Publicando en Instagram Stories...", chat_id=call.message.chat.id, message_id=call.message.message_id)
                success, result = publish_to_instagram(product["raw_url"])
                if success:
                    bot.send_message(call.message.chat.id, f"🎉 ¡Publicado con éxito! ID: `{result}`", parse_mode="Markdown")
                else:
                    bot.send_message(call.message.chat.id, f"❌ Error en API Instagram: `{result}`", parse_mode="Markdown")
            elif call.data.startswith("ord_"):
                bot.edit_message_caption("⏳ Generando y Publicando versión 'A Pedido'...", chat_id=call.message.chat.id, message_id=call.message.message_id)
                new_image_path = create_story_template(product, img_obj, mode="ENCARGO")
                success, result = publish_to_instagram(product["raw_url"])
                if success:
                    bot.send_message(call.message.chat.id, f"🎉 ¡Publicado modo 'A Pedido'! ID: `{result}`", parse_mode="Markdown")
                else:
                    bot.send_message(call.message.chat.id, f"❌ Error en API Instagram: `{result}`", parse_mode="Markdown")
            elif call.data == "skip":
                bot.edit_message_caption("⏩ Publicación salteada por el usuario.", chat_id=call.message.chat.id, message_id=call.message.message_id)
                
            user_action["done"] = True

        # Polling limitado de 180 segundos para darte tiempo a responder en Telegram sin colgar GitHub
        start_time = time.time()
        while not user_action["done"] and (time.time() - start_time) < 180:
            try:
                bot.get_updates(offset=-1, timeout=2)
            except Exception:
                pass
            time.sleep(1)

        if not user_action["done"]:
            bot.edit_message_caption("⏱️ Tiempo de espera agotado sin acción.", chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id)
            
        if os.path.exists(image_path):
            os.remove(image_path)

    except Exception as e:
        print(f"Error procesando producto: {e}")

if __name__ == "__main__":
    interactive_process()
