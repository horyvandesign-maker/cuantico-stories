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

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

SITE_URL = "https://cuanticopc.com.ar"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None

ACCENT_COLORS = ["#00FF88", "#00E5FF", "#B000FF"]
ON_DEMAND_COLOR = "#FFB703"

user_choice = {"action": None}

@bot.callback_query_handler(func=lambda call: True)
def global_callback_listener(call):
    if call.data.startswith("approve_"):
        user_choice["action"] = "approve"
        bot.answer_callback_query(call.id, "Publicando...")
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption="🚀 *Publicando diseño final en Instagram Stories...*", parse_mode="Markdown")
    elif call.data.startswith("skip_"):
        user_choice["action"] = "skip"
        bot.answer_callback_query(call.id, "Salteado.")
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption="⏭️ *Producto salteado.*", parse_mode="Markdown")
    elif call.data == "stop":
        user_choice["action"] = "stop"
        bot.answer_callback_query(call.id, "Deteniendo proceso...")
        bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption="🛑 *Proceso detenido.*", parse_mode="Markdown")
    
    bot.stop_polling()

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
        print(f"Fallback a título original: {e}")
        return original_title

def fetch_all_catalog_products():
    # Cambiamos al endpoint oficial v3 de WooCommerce REST API
    endpoint = f"{SITE_URL}/wp-json/wc/v3/products"
    
    # Si usás llaves de API las pones en params, si es pública podés hacer la petición directa:
    catalog = []
    page = 1
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cache-Control": "no-cache"
    }

    while True:
        params = {
            "per_page": 50, 
            "page": page,
            "_fields": "id,name,price,regular_price,stock_status,backorders_allowed,images",
            "_nocache": int(time.time())
        }
        
        # En caso de requerir autenticación básica si la v3 está protegida:
        # res = requests.get(endpoint, params=params, auth=(WC_KEY, WC_SECRET), timeout=15)
        res = requests.get(endpoint, params=params, headers=headers, timeout=15)
        
        if res.status_code != 200 or not res.json():
            # FALLBACK DE EMERGENCIA: Si la v3 requiere auth y devuelve 401, usamos Store API analizando el HTML
            break
            
        items = res.json()
        if not items:
            break
            
        for product in items:
            images = product.get("images", [])
            if not images:
                continue

            # API v3 expone estas variables tal cual están en la base de datos:
            stock_status = str(product.get("stock_status", "")).lower() # 'instock', 'outofstock', 'onbackorder'
            backorders_allowed = product.get("backorders_allowed", False)
            raw_price = product.get("price", "")

            try:
                price_val = float(raw_price) if raw_price else 0
            except ValueError:
                price_val = 0

            # CRITERIO DE EVALUACIÓN DIRECTO Y EXACTO
            is_backorder = (stock_status == "onbackorder") or backorders_allowed
            is_out_of_stock = (stock_status == "outofstock")
            
            if is_backorder or is_out_of_stock or price_val <= 0:
                is_on_demand = True
                formatted_price = "POR ENCARGUE"
            else:
                is_on_demand = False
                formatted_price = f"${price_val:,.0f}".replace(",", ".")

            catalog.append({
                "id": product.get("id"),
                "original_name": clean_text(product.get("name", "Producto Cuantico")),
                "price": formatted_price,
                "is_on_demand": is_on_demand,
                "raw_url": images[0].get("src", "")
            })
            
        page += 1

    print(f"Total productos en catálogo a procesar: {len(catalog)}")
    return catalog

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

def create_story_template(product, img_obj):
    canvas_w, canvas_h = 1080, 1920
    
    if product["is_on_demand"]:
        accent_color = ON_DEMAND_COLOR
        display_label = ">> PRODUCTO POR ENCARGUE <<"
        cta_text = "-> Respondé 'QUIERO' por DM o buscalo en cuanticopc.com.ar <-"
    else:
        accent_color = random.choice(ACCENT_COLORS)
        display_label = product["price"]
        cta_text = "🔗 Link a la tienda en la Bio | cuanticopc.com.ar"
    
    bg = img_obj.resize((canvas_w, canvas_h)).filter(ImageFilter.GaussianBlur(50))
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (12, 12, 18, 160))
    bg.paste(overlay, (0, 0), overlay)
    
    gradient_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(gradient_layer)
    draw_vertical_gradient(g_draw, (0, 0, canvas_w, 350), (0, 0, 0, 210), (0, 0, 0, 0))
    draw_vertical_gradient(g_draw, (0, canvas_h - 400, canvas_w, canvas_h), (0, 0, 0, 0), (0, 0, 0, 240))
    bg.paste(gradient_layer, (0, 0), gradient_layer)
    
    card_w, card_h = 860, 860
    card_x = (canvas_w - card_w) // 2
    card_y = 400
    
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
    
    logo_path = os.path.join(os.path.dirname(__file__), "logo_canva.png")
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img.thumbnail((550, 220))
            l_w, l_h = logo_img.size
            chosen_pos = random.choice(["left", "center", "right"])
            
            if chosen_pos == "left":
                logo_x = 50
            elif chosen_pos == "right":
                logo_x = canvas_w - l_w - 50
            else:
                logo_x = (canvas_w - l_w) // 2
                
            logo_y = 100
            bg.paste(logo_img, (logo_x, logo_y), logo_img)
        except Exception:
            draw.text((canvas_w // 2, 150), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")
    else:
        draw.text((canvas_w // 2, 150), "CUANTICO PC", fill="#FFFFFF", font=get_font(50), anchor="mm")
    
    font_title = get_font(40)
    wrapped_lines = textwrap.wrap(product["ai_name"], width=24)
    wrapped_text = "\n".join(wrapped_lines[:2])
    
    title_y = card_y + card_h + 80
    draw.multiline_text((canvas_w // 2, title_y), wrapped_text, fill="#FFFFFF", font=font_title, anchor="mm", align="center")
    
    font_size = 38 if product["is_on_demand"] else 56
    font_badge = get_font(font_size)
    
    bbox = draw.textbbox((0, 0), display_label, font=font_badge)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    
    badge_padding_x = 40
    badge_padding_y = 20
    badge_w = text_w + (badge_padding_x * 2)
    badge_h = text_h + (badge_padding_y * 2)
    
    badge_x1 = (canvas_w - badge_w) // 2
    badge_y1 = title_y + 90
    badge_x2 = badge_x1 + badge_w
    badge_y2 = badge_y1 + badge_h
    
    draw.rounded_rectangle((badge_x1, badge_y1, badge_x2, badge_y2), radius=25, fill=(18, 22, 28, 240), outline=accent_color, width=3)
    draw.text(((badge_x1 + badge_x2) // 2, (badge_y1 + badge_y2) // 2 - 3), display_label, fill=accent_color, font=font_badge, anchor="mm")
    
    # BANNER FLOTANTE INFERIOR CON LLAMADO A LA ACCIÓN (CTA)
    cta_box_w, cta_box_h = 980, 85
    cta_x1 = (canvas_w - cta_box_w) // 2
    cta_y1 = canvas_h - 170
    cta_x2 = cta_x1 + cta_box_w
    cta_y2 = cta_y1 + cta_box_h
    
    draw.rounded_rectangle((cta_x1, cta_y1, cta_x2, cta_y2), radius=20, fill=(0, 0, 0, 180), outline="#444444", width=2)
    
    font_cta = get_font(28)
    draw.text((canvas_w // 2, (cta_y1 + cta_y2) // 2), cta_text, fill="#EEEEEE", font=font_cta, anchor="mm")
    
    output_path = f"story_{product['id']}.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path
    
def upload_local_image_to_web(local_filepath):
    """
    Sube la imagen armada a una pasarela alternativa ultra estable (FreeImage.host)
    """
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

    # Fallback 2: Subida por transferencia
    try:
        with open(local_filepath, "rb") as file:
            res = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": file}, timeout=15)
            data = res.json()
            if "data" in data and "url" in data["data"]:
                # Convertir URL de vista previa a URL directa de imagen
                direct_url = data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/")
                return direct_url
    except Exception as e:
        print(f"Error en servidor secundario de imágenes: {e}")

    return None

def publish_to_instagram(local_image_path):
    public_image_url = upload_local_image_to_web(local_image_path)
    
    if not public_image_url:
        return False, "No se pudo obtener una URL pública para la plantilla armada."

    container_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
    payload = {"image_url": public_image_url, "media_type": "STORIES", "access_token": ACCESS_TOKEN}
    
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
    products = fetch_all_catalog_products()
    if not products:
        bot.send_message(TELEGRAM_CHAT_ID, "❌ No se encontraron productos.")
        return

    headers = {"User-Agent": "Mozilla/5.0"}
    total = len(products)
    
    bot.send_message(TELEGRAM_CHAT_ID, f"🚀 *Catálogo preparado:* {total} productos en total.", parse_mode="Markdown")

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
                InlineKeyboardButton("✅ Publicar Story", callback_data=f"approve_{prod['id']}"),
                InlineKeyboardButton("⏭️ Saltear", callback_data=f"skip_{prod['id']}"),
                InlineKeyboardButton("🛑 Detener", callback_data="stop")
            )
            
            type_str = "📦 POR ENCARGUE" if prod["is_on_demand"] else f"💰 {prod['price']}"
            caption = (
                f"📦 *[{index}/{total}] {prod['original_name']}*\n"
                f"Estado asignado: *{type_str}*\n\n"
                f"¿Deseas enviar esta Story a Instagram?"
            )
            
            with open(image_path, "rb") as photo:
                bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
                
            user_choice["action"] = None
            bot.polling(timeout=300, non_stop=False)
            
            if user_choice["action"] == "approve":
                success, result = publish_to_instagram(image_path)
                if success:
                    bot.send_message(TELEGRAM_CHAT_ID, "🎉 ¡Publicado con éxito el diseño final en Instagram Stories!", parse_mode="Markdown")
                else:
                    bot.send_message(TELEGRAM_CHAT_ID, f"❌ Error Meta: `{result}`", parse_mode="Markdown")
                time.sleep(3)
                
            elif user_choice["action"] == "stop":
                bot.send_message(TELEGRAM_CHAT_ID, "🏁 *Proceso detenido.*", parse_mode="Markdown")
                if os.path.exists(image_path):
                    os.remove(image_path)
                break

            if os.path.exists(image_path):
                os.remove(image_path)
                
        except Exception as e:
            print(f"Error procesando producto {prod['id']}: {e}")
            continue

if __name__ == "__main__":
    process_catalog()
