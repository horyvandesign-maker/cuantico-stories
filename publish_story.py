import os
import time
import html
import textwrap
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
    """Obtiene todos los productos con precio válido e imagen desde WooCommerce."""
    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    valid_products = []
    page = 1
    
    while True:
        res = requests.get(endpoint, params={"per_page": 50, "page": page}, headers=headers, timeout=15)
        if res.status_code != 200 or not res.json():
            break
            
        items = res.json()
        if not items:
            break
            
        for product in items:
            images = product.get("images", [])
            if not images:
                continue
                
            prices_info = product.get("prices", {})
            raw_price = prices_info.get("price", "0")
            
            # Filtrar estrictamente productos que tengan un precio numérico válido > 0
            if not str(raw_price).isdigit() or int(raw_price) <= 0:
                continue
                
            val_num = int(raw_price)
            # Formatear precio dividiendo los centavos
            val_final = val_num / 100
            formatted_price = f"${val_final:,.0f}".replace(",", ".")
            
            valid_products.append({
                "id": product.get("id"),
                "original_name": clean_text(product.get("name", "Producto Cuantico")),
                "price": formatted_price,
                "raw_url": images[0].get("src", "")
            })
            
        page += 1

    print(f"Se encontraron {len(valid_products)} productos con precio válido.")
    return valid_products

def create_story_template(product, img_obj):
    """Genera la plantilla visual de 1080x1920 px."""
    canvas_w, canvas_h = 1080, 1920
    
    bg = img_obj.resize((canvas_w, canvas_h))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 180))
    bg.paste(overlay, (0, 0), overlay)
    
    img_obj.thumbnail((800, 800))
    p_w, p_h = img_obj.size
    offset_x = (canvas_w - p_w) // 2
    offset_y = (canvas_h - p_h) // 2 - 120
    bg.paste(img_obj, (offset_x, offset_y))
    
    draw = ImageDraw.Draw(bg)
    
    font_brand = get_font(50)
    font_title = get_font(44)
    font_price = get_font(65)
    font_footer = get_font(38)
    
    draw.text((canvas_w // 2, 160), "CUANTICO PC", fill="#FFFFFF", font=font_brand, anchor="mm")
    
    wrapped_lines = textwrap.wrap(product["ai_name"], width=24)
    wrapped_text = "\n".join(wrapped_lines[:3])
    
    draw.multiline_text(
        (canvas_w // 2, offset_y + p_h + 100), 
        wrapped_text, 
        fill="#F0F0F0", 
        font=font_title, 
        anchor="mm", 
        align="center"
    )
    
    draw.text((canvas_w // 2, offset_y + p_h + 230), product["price"], fill="#00FF88", font=font_price, anchor="mm")
    draw.text((canvas_w // 2, canvas_h - 180), "cuanticopc.com.ar", fill="#CCCCCC", font=font_footer, anchor="mm")
    
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
            # Descargar la imagen del producto
            img_res = requests.get(prod["raw_url"], headers=headers, timeout=10)
            if img_res.status_code != 200:
                continue
                
            img_obj = Image.open(BytesIO(img_res.content)).convert("RGB")
            
            # Generar título por IA
            prod["ai_name"] = generate_ai_title(prod["original_name"])
            
            # Generar la imagen preview
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
            
            # Capturar la respuesta del botón en Telegram
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

            # Esperar interacción del usuario (hasta 5 minutos por producto)
            bot.polling(timeout=300, non_stop=False)
            
            # Limpiar archivo temporal
            if os.path.exists(image_path):
                os.remove(image_path)
                
            if user_choice["action"] == "approve":
                success, result = publish_to_instagram(prod["raw_url"])
                if success:
                    bot.send_message(TELEGRAM_CHAT_ID, f"🎉 ¡Publicado exitosamente en Instagram!", parse_mode="Markdown")
                else:
                    bot.send_message(TELEGRAM_CHAT_ID, f"❌ Error al publicar en Meta: `{result}`", parse_mode="Markdown")
                time.sleep(3) # Pausa entre publicaciones
                
            elif user_choice["action"] == "stop":
                bot.send_message(TELEGRAM_CHAT_ID, "🏁 *Secuencia finalizada por el usuario.*", parse_mode="Markdown")
                break
                
        except Exception as e:
            print(f"Error procesando producto {prod['id']}: {e}")
            continue

if __name__ == "__main__":
    process_catalog()
