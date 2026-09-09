import os
import time
import html
import json
import textwrap
import random
import requests
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from google import genai

# ==========================================
# CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ==========================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

SITE_URL = "https://cuanticopc.com.ar"
HISTORY_FILE = "published_history.json"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

# PALETA CYBERPUNK EXPANDIDA (Múltiples colores Neón aleatorios)
CYBER_PALETTE = ["#00FF88", "#00E5FF", "#B000FF", "#FF0055", "#FF5722", "#00FFFF", "#76FF03"]
ON_DEMAND_COLOR = "#FFB703"

user_choice = {"action": None}

# ==========================================
# HISTORIAL
# ==========================================
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_to_history(product_id):
    history = load_history()
    if product_id not in history:
        history.append(product_id)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history[-200:], f)

# ==========================================
# BOT LISTENERS
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def global_callback_listener(call):
    if call.data.startswith("approve_"):
        user_choice["action"] = "approve"
        bot.answer_callback_query(call.id, "Publicando...")
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption="🚀 <b>Publicando diseño final en Instagram Stories...</b>", parse_mode="HTML")
    elif call.data.startswith("skip_"):
        user_choice["action"] = "skip"
        bot.answer_callback_query(call.id, "Salteado.")
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption="⏭️ <b>Producto salteado.</b>", parse_mode="HTML")
    elif call.data == "stop":
        user_choice["action"] = "stop"
        bot.answer_callback_query(call.id, "Deteniendo proceso...")
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption="🛑 <b>Proceso detenido.</b>", parse_mode="HTML")
    
    bot.stop_polling()

# ==========================================
# UTILIDADES GRÁFICAS Y TEXTO
# ==========================================
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

def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))

def draw_neon_glow_line(draw_obj, points, color_rgb, width=6, glow_intensity=4):
    for i in range(glow_intensity, 0, -1):
        alpha = int(255 / (i * 1.5))
        w = width + (i * 6)
        draw_obj.line(points, fill=(color_rgb[0], color_rgb[1], color_rgb[2], alpha), width=w)
    draw_obj.line(points, fill=(255, 255, 255, 240), width=width)

def draw_random_cyber_lines(t_draw, canvas_w, canvas_h):
    """Genera líneas y HUDs neón completamente aleatorios y multicolores en cada ejecución"""
    for _ in range(4): # Cantidad de formaciones aleatorias
        color_hex = random.choice(CYBER_PALETTE)
        accent_rgb = hex_to_rgb(color_hex)
        
        # Posición aleatoria en esquinas o laterales
        quadrant = random.choice(["top_left", "top_right", "bottom_left", "bottom_right"])
        
        if quadrant == "top_left":
            x = random.randint(0, 80)
            y = random.randint(180, 280)
            points = [(x, y), (x + random.randint(120, 240), y), (x + random.randint(220, 340), y + random.randint(70, 130))]
        elif quadrant == "top_right":
            x = random.randint(canvas_w - 80, canvas_w)
            y = random.randint(180, 280)
            points = [(x, y), (x - random.randint(120, 240), y), (x - random.randint(220, 340), y + random.randint(70, 130))]
        elif quadrant == "bottom_left":
            x = random.randint(0, 80)
            y = random.randint(canvas_h - 380, canvas_h - 260)
            points = [(x, y), (x + random.randint(120, 240), y), (x + random.randint(220, 340), y - random.randint(70, 130))]
        else:
            x = random.randint(canvas_w - 80, canvas_w)
            y = random.randint(canvas_h - 380, canvas_h - 260)
            points = [(x, y), (x - random.randint(120, 240), y), (x - random.randint(220, 340), y - random.randint(70, 130))]
            
        w_val = random.randint(4, 7)
        glow_val = random.randint(3, 5)
        draw_neon_glow_line(t_draw, points, accent_rgb, width=w_val, glow_intensity=glow_val)
        
        # Nodo o punto tecnológico en el vértice final
        end_pt = points[-1]
        t_draw.ellipse((end_pt[0]-6, end_pt[1]-6, end_pt[0]+6, end_pt[1]+6), fill=(255, 255, 255, 255), outline=accent_rgb, width=2)

# ==========================================
# INTELIGENCIA ARTIFICIAL (Gemini)
# ==========================================
def generate_ai_title(original_title, permalink=""):
    if not GEMINI_API_KEY:
        return original_title
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            f"Analizá este producto de tecnología: '{original_title}'. "
            f"Crea un título comercial directo e irresistible para una Instagram Story. "
            f"REGLAS: Máximo 6 palabras, sin emojis, sin comillas, en español latino."
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

# ==========================================
# WOOCOMMERCE CATALOG FETCH
# ==========================================
def fetch_all_catalog_products():
    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache"
    }
    
    catalog = []
    page = 1
    history = load_history()
    
    while True:
        params = {"per_page": 50, "page": page, "_nocache": int(time.time())}
        res = requests.get(endpoint, params=params, headers=headers, timeout=15)
        if res.status_code != 200 or not res.json():
            break
            
        items = res.json()
        if not items:
            break
            
        for product in items:
            prod_id = product.get("id")
            if prod_id in history:
                continue

            images = product.get("images", [])
            if not images:
                continue

            prices_info = product.get("prices", {})
            raw_price = prices_info.get("price")
            
            is_in_stock = product.get("is_in_stock", True)
            is_on_backorder = product.get("is_on_backorder", False)
            is_purchasable = product.get("is_purchasable", True)

            price_val = 0
            if raw_price is not None and str(raw_price).strip() != "":
                try:
                    price_val = int(raw_price)
                except ValueError:
                    price_val = 0

            if not is_in_stock or is_on_backorder or not is_purchasable or price_val <= 0:
                is_on_demand = True
                formatted_price = "POR ENCARGUE"
            else:
                is_on_demand = False
                val_final = price_val / 100
                formatted_price = f"${val_final:,.0f}".replace(",", ".")

            catalog.append({
                "id": prod_id,
                "original_name": clean_text(product.get("name", "Producto Cuantico")),
                "price": formatted_price,
                "is_on_demand": is_on_demand,
                "raw_url": images[0].get("src", ""),
                "permalink": product.get("permalink", SITE_URL)
            })
            
        page += 1

    print(f"Total productos en catálogo a procesar: {len(catalog)}")
    return catalog

# ==========================================
# MOTOR GRÁFICO (Plantilla con Líneas Aleatorias y Multicolor)
# ==========================================
def create_story_template(product, img_obj):
    canvas_w, canvas_h = 1080, 1920
    
    if product["is_on_demand"]:
        accent_hex = ON_DEMAND_COLOR
        display_label = ">> PRODUCTO POR ENCARGUE <<"
        cta_text = "Respondé 'QUIERO' por DM o tocá el enlace"
    else:
        accent_hex = random.choice(CYBER_PALETTE)
        display_label = product["price"]
        cta_text = "Tocá la tarjeta para ver en la tienda"
        
    accent_rgb = hex_to_rgb(accent_hex)
    
    # Fondo Oscuro
    bg = img_obj.resize((canvas_w, canvas_h)).filter(ImageFilter.GaussianBlur(80))
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (8, 9, 14, 215))
    bg.paste(overlay, (0, 0), overlay)
    
    # Capa de vectores Neón aleatorios y multicolores
    tech_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(tech_layer)
    draw_random_cyber_lines(t_draw, canvas_w, canvas_h)
    bg.paste(tech_layer, (0, 0), tech_layer)

    # Tarjeta Central y Glow
    card_w, card_h = 860, 860
    card_x = (canvas_w - card_w) // 2
    card_y = 410
    
    glow_bg = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow_bg)
    g_draw.ellipse((card_x + 80, card_y + 80, card_x + card_w - 80, card_y + card_h - 80), 
                   fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 110))
    glow_bg = glow_bg.filter(ImageFilter.GaussianBlur(65))
    bg.paste(glow_bg, (0, 0), glow_bg)
    
    card_border = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    cb_draw = ImageDraw.Draw(card_border)
    cb_draw.rounded_rectangle((card_x - 6, card_y - 6, card_x + card_w + 6, card_y + card_h + 6), 
                              radius=32, fill=None, outline=accent_rgb, width=5)
    card_border = card_border.filter(ImageFilter.GaussianBlur(5))
    bg.paste(card_border, (0, 0), card_border)

    card_bg = Image.new("RGBA", (card_w, card_h), (255, 255, 255, 248))
    card_mask = Image.new("L", (card_w, card_h), 0)
    card_mask_draw = ImageDraw.Draw(card_mask)
    card_mask_draw.rounded_rectangle((0, 0, card_w, card_h), radius=30, fill=255)
    bg.paste(card_bg, (card_x, card_y), card_mask)

    # Producto
    img_copy = img_obj.copy()
    img_copy.thumbnail((760, 760))
    p_w, p_h = img_copy.size
    p_x = card_x + (card_w - p_w) // 2
    p_y = card_y + (card_h - p_h) // 2
    bg.paste(img_copy, (p_x, p_y), img_copy if img_copy.mode == "RGBA" else None)

    draw = ImageDraw.Draw(bg)

    # Logotipo
    logo_path = os.path.join(os.path.dirname(__file__), "logo_canva.png")
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img.thumbnail((550, 200))
            l_w, l_h = logo_img.size
            logo_x = (canvas_w - l_w) // 2
            bg.paste(logo_img, (logo_x, 160), logo_img)
        except Exception:
            draw.text((canvas_w // 2, 180), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")
    else:
        draw.text((canvas_w // 2, 180), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")

    # Título
    font_title = get_font(42)
    wrapped_lines = textwrap.wrap(product["ai_name"], width=22)
    wrapped_text = "\n".join(wrapped_lines[:2])
    
    title_y = card_y + card_h + 80
    draw.multiline_text((canvas_w // 2, title_y), wrapped_text, fill="#FFFFFF", font=font_title, anchor="mm", align="center")

    # Badge de Precio / Encargue
    font_size = 36 if product["is_on_demand"] else 54
    font_badge = get_font(font_size)
    
    bbox = draw.textbbox((0, 0), display_label, font=font_badge)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    badge_w = text_w + 100
    badge_h = text_h + 46
    badge_x1 = (canvas_w - badge_w) // 2
    badge_y1 = title_y + 85
    badge_x2 = badge_x1 + badge_w
    badge_y2 = badge_y1 + badge_h

    draw.rounded_rectangle((badge_x1 - 2, badge_y1 - 2, badge_x2 + 2, badge_y2 + 2), radius=22, fill=accent_rgb)
    draw.rounded_rectangle((badge_x1, badge_y1, badge_x2, badge_y2), radius=20, fill=(12, 14, 20, 255))
    draw.text(((badge_x1 + badge_x2) // 2, (badge_y1 + badge_y2) // 2 - 2), display_label, fill=accent_hex, font=font_badge, anchor="mm")

    # Banner CTA inferior
    cta_box_w, cta_box_h = 960, 80
    cta_x1 = (canvas_w - cta_box_w) // 2
    cta_y1 = canvas_h - 220
    cta_x2 = cta_x1 + cta_box_w
    cta_y2 = cta_y1 + cta_box_h

    draw.rounded_rectangle((cta_x1, cta_y1, cta_x2, cta_y2), radius=16, fill=(15, 18, 25, 230), outline=accent_hex, width=2)
    
    font_cta = get_font(28)
    draw.text((canvas_w // 2, (cta_y1 + cta_y2) // 2), cta_text, fill="#FFFFFF", font=font_cta, anchor="mm")

    output_path = f"story_{product['id']}.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path

# ==========================================
# PUBLICACIÓN WEB / INSTAGRAM (Con diagnóstico de Link Sticker)
# ==========================================
def upload_local_image_to_web(local_filepath):
    url = "https://freeimage.host/api/1/upload"
    try:
        with open(local_filepath, "rb") as file:
            payload = {"key": "6d207e02198a847aa98d0a2a901485a5", "action": "upload", "format": "json"}
            files = {"source": file}
            res = requests.post(url, data=payload, files=files, timeout=20)
            data = res.json()
            if res.status_code == 200 and "image" in data and "url" in data["image"]:
                return data["image"]["url"]
    except Exception as e:
        print(f"Error en servidor principal de imágenes: {e}")

    try:
        with open(local_filepath, "rb") as file:
            res = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": file}, timeout=15)
            data = res.json()
            if "data" in data and "url" in data["data"]:
                return data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception as e:
        print(f"Error en servidor secundario de imágenes: {e}")

    return None

def publish_to_instagram(local_image_path, product_link):
    public_image_url = upload_local_image_to_web(local_image_path)
    
    if not public_image_url:
        return False, "No se pudo obtener una URL pública para la imagen."

    container_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
    
    # Configuración del sticker de enlace nativo de Instagram
    link_sticker = {
        "link_material_option": 0,
        "url": product_link,
        "x": 0.5,
        "y": 0.5,
        "width": 0.5,
        "height": 0.1,
        "rotation": 0.0
    }
    
    payload = {
        "image_url": public_image_url,
        "media_type": "STORIES",
        "story_sticker_ids": json.dumps([link_sticker]),
        "access_token": ACCESS_TOKEN
    }
    
    res = requests.post(container_url, data=payload)
    res_data = res.json()
    
    # Si la API rechaza el sticker de enlace, imprimimos el error exacto en consola para diagnosticar
    if "id" not in res_data:
        print(f"⚠️ Meta rechazó el sticker de enlace (Story se publicará sin enlace): {res_data}")
        payload.pop("story_sticker_ids", None)
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

# ==========================================
# CICLO PRINCIPAL
# ==========================================
def process_catalog(auto_approve=False):
    products = fetch_all_catalog_products()
    if not products:
        if bot:
            bot.send_message(TELEGRAM_CHAT_ID, "❌ No hay productos nuevos para publicar.")
        return

    headers = {"User-Agent": "Mozilla/5.0"}
    total = len(products)
    
    if bot:
        bot.send_message(TELEGRAM_CHAT_ID, f"🚀 <b>Catálogo preparado:</b> {total} productos sin publicar.", parse_mode="HTML")

    for index, prod in enumerate(products, start=1):
        try:
            img_res = requests.get(prod["raw_url"], headers=headers, timeout=10)
            if img_res.status_code != 200:
                continue
                
            img_obj = Image.open(BytesIO(img_res.content)).convert("RGB")
            
            prod["ai_name"] = generate_ai_title(prod["original_name"], prod["permalink"])
            image_path = create_story_template(prod, img_obj)
            
            if auto_approve:
                success, result = publish_to_instagram(image_path, prod["permalink"])
                if success:
                    save_to_history(prod["id"])
                    print(f"[{index}/{total}] Publicado automáticamente en IG.")
                if os.path.exists(image_path):
                    os.remove(image_path)
                time.sleep(10)
                continue

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Publicar Story", callback_data=f"approve_{prod['id']}"),
                InlineKeyboardButton("⏭️ Saltear", callback_data=f"skip_{prod['id']}"),
                InlineKeyboardButton("🛑 Detener", callback_data="stop")
            )
            
            type_str = "📦 POR ENCARGUE" if prod["is_on_demand"] else f"💰 {prod['price']}"
            
            caption = (
                f"📦 <b>[{index}/{total}] {html.escape(prod['original_name'])}</b>\n"
                f"Estado asignado: <b>{type_str}</b>\n"
                f"🔗 <a href='{prod['permalink']}'>Ver en Tienda</a>\n\n"
                f"¿Deseas enviar esta Story a Instagram?"
            )
            
            with open(image_path, "rb") as photo:
                bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, reply_markup=markup, parse_mode="HTML")
                
            user_choice["action"] = None
            bot.polling(timeout=300, non_stop=False)
            
            if user_choice["action"] == "approve":
                success, result = publish_to_instagram(image_path, prod["permalink"])
                if success:
                    save_to_history(prod["id"])
                    bot.send_message(TELEGRAM_CHAT_ID, "🎉 <b>¡Publicado con éxito en Instagram Stories!</b>", parse_mode="HTML")
                else:
                    bot.send_message(TELEGRAM_CHAT_ID, f"❌ Error Meta: <code>{result}</code>", parse_mode="HTML")
                time.sleep(3)
                
            elif user_choice["action"] == "stop":
                bot.send_message(TELEGRAM_CHAT_ID, "🏁 <b>Proceso detenido.</b>", parse_mode="HTML")
                if os.path.exists(image_path):
                    os.remove(image_path)
                break

            if os.path.exists(image_path):
                os.remove(image_path)
                
        except Exception as e:
            print(f"Error procesando producto {prod['id']}: {e}")
            continue

if __name__ == "__main__":
    process_catalog(auto_approve=False)
