import os
import time
import html
import textwrap
import random
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import telebot
from google import genai

# Credenciales desde Variables de Entorno / Secrets
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
            images = product.get("images", [])
            if not images:
                continue
            if product.get("stock_status") == "outofstock" or not product.get("is_in_stock", True):
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

    print(f"Productos válidos encontrados: {len(valid_products)}")
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

def draw_cyber_grid(draw_obj, rect):
    x1, y1, x2, y2 = rect
    grid_color = (138, 43, 226, random.randint(40, 80))
    for i in range(0, 200, 25):
        draw_obj.line([(x1, y1 + i), (x2, y1 + i)], fill=grid_color, width=1)
    center_x = (x1 + x2) // 2
    for offset in range(-600, 700, 80):
        draw_obj.line([(center_x + offset // 3, y1), (center_x + offset, y2)], fill=grid_color, width=1)

def create_story_template(product, img_obj):
    canvas_w, canvas_h = 1080, 1920
    accent_color = random.choice(ACCENT_COLORS)
    header_text = random.choice(HEADER_TAGS)
    
    bg = Image.new("RGBA", (canvas_w, canvas_h), (10, 8, 20, 255))
    g_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(g_layer)
    draw_vertical_gradient(g_draw, (0, 0, canvas_w, canvas_h), (18, 12, 38, 255), (6, 5, 15, 255))
    bg.paste(g_layer, (0, 0), g_layer)
    
    cyber_draw = ImageDraw.Draw(bg)
    draw_cyber_grid(cyber_draw, (0, canvas_h - 250, canvas_w, canvas_h))
    
    font_header = get_font(34)
    cyber_draw.text((70, 65), header_text, fill="#FFFFFF", font=font_header)
    
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
    
    draw = ImageDraw.Draw(bg)
    
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
    
    # LEYENDA AUTOMÁTICA DE LINK EN BIO
    draw.text((70, canvas_h - 110), "🔗 COMPRÁ CON EL LINK EN BIO O ESCRIBINOS POR PRIVADO", fill="#00E5FF", font=get_font(25))
    draw.text((70, canvas_h - 65), "@CUANTICOPC", fill="#FFFFFF", font=get_font(32))
    
    output_path = f"story_{product['id']}.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path

def publish_to_instagram(image_url):
    """Envía la imagen a Instagram mediante Meta API."""
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

def process_catalog():
    products = fetch_all_valid_products()
    if not products:
        if bot and TELEGRAM_CHAT_ID:
            bot.send_message(TELEGRAM_CHAT_ID, "❌ No se encontraron productos válidos.")
        return

    # Si se ejecuta por Action manual o Cron, tomamos un producto o procesamos lote
    product = random.choice(products) # Publica 1 producto aleatorio por ejecución
    
    if bot and TELEGRAM_CHAT_ID:
        bot.send_message(TELEGRAM_CHAT_ID, f"🚀 *Procesando producto:* {product['original_name']}\n💰 {product['price']}", parse_mode="Markdown")

    try:
        img_res = requests.get(product["raw_url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if img_res.status_code == 200:
            img_obj = Image.open(BytesIO(img_res.content)).convert("RGB")
            product["ai_name"] = generate_ai_title(product["original_name"])
            
            image_path = create_story_template(product, img_obj)
            
            # Notificación a Telegram con la imagen generada
            if bot and TELEGRAM_CHAT_ID:
                with open(image_path, "rb") as photo:
                    bot.send_photo(
                        TELEGRAM_CHAT_ID, 
                        photo, 
                        caption=f"📸 *Story Generada e Intentando Publicación*\n📦 {product['original_name']}\n💰 {product['price']}\n🔗 Link: {product['permalink']}", 
                        parse_mode="Markdown"
                    )
            
            # Publicación directa en Instagram
            success, result = publish_to_instagram(product["raw_url"])
            
            if success:
                msg = f"🎉 ¡Publicado exitosamente en Instagram Stories! (ID: `{result}`)"
            else:
                msg = f"⚠️ Generado pero error en API Instagram: `{result}`"
                
            if bot and TELEGRAM_CHAT_ID:
                bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode="Markdown")
                
            if os.path.exists(image_path):
                os.remove(image_path)
    except Exception as e:
        print(f"Error durante el proceso: {e}")

if __name__ == "__main__":
    process_catalog()
