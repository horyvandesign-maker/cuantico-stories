import os
import random
import time
import html
import requests
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

SITE_URL = "https://cuanticopc.com.ar"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

def get_font(size):
    """Descarga e instala una fuente legible en alta resolución."""
    font_path = "Roboto-Bold.ttf"
    if not os.path.exists(font_path):
        url = "https://github.com/google/fonts/raw/main/ofl/roboto/static/Roboto-Bold.ttf"
        res = requests.get(url)
        with open(font_path, "wb") as f:
            f.write(res.content)
    return ImageFont.truetype(font_path, size)

def clean_text(text):
    """Limpia caracteres especiales e inconsistencias de HTML."""
    decoded = html.unescape(text)
    return decoded.replace('"', "'").replace("”", "'").strip()

def get_product_and_image():
    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    res = requests.get(endpoint, params={"per_page": 50}, headers=headers, timeout=15)
    if res.status_code != 200 or not res.json():
        print("Error al consultar WooCommerce.")
        exit(1)
        
    products = res.json()
    random.shuffle(products)
    
    for product in products:
        images = product.get("images", [])
        if not images:
            continue
            
        img_url = images[0].get("src", "")
        try:
            img_res = requests.get(img_url, headers=headers, timeout=10)
            if img_res.status_code == 200:
                img_orig = Image.open(BytesIO(img_res.content)).convert("RGB")
                
                price_raw = product.get("prices", {}).get("price", "0")
                price = f"${int(price_raw) / 100:,.0f}".replace(",", ".") if str(price_raw).isdigit() else "$ Consultar"
                
                raw_name = product.get("name", "Producto Cuantico")
                
                return {
                    "name": clean_text(raw_name),
                    "price": price,
                    "img_obj": img_orig,
                    "raw_url": img_url
                }
        except Exception as e:
            continue

    print("No se encontró ningún producto con imagen procesable.")
    exit(1)

def create_story_template(product):
    """Genera el lienzo vertical de 1080x1920 px con textos grandes."""
    canvas_w, canvas_h = 1080, 1920
    img_orig = product["img_obj"]
    
    # 1. Fondo Oscuro
    bg = img_orig.resize((canvas_w, canvas_h))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 180))
    bg.paste(overlay, (0, 0), overlay)
    
    # 2. Rescalar Imagen
    img_orig.thumbnail((880, 880))
    p_w, p_h = img_orig.size
    offset_x = (canvas_w - p_w) // 2
    offset_y = (canvas_h - p_h) // 2 - 120
    bg.paste(img_orig, (offset_x, offset_y))
    
    # 3. Dibujar Fuentes Gigantes
    draw = ImageDraw.Draw(bg)
    
    font_brand = get_font(55)
    font_title = get_font(48)
    font_price = get_font(75)
    font_footer = get_font(40)
    
    # Encabezado Marca
    draw.text((canvas_w // 2, 160), "CUANTICO PC", fill="#FFFFFF", font=font_brand, anchor="mm")
    
    # Nombre Producto
    title_text = product["name"]
    if len(title_text) > 40:
        title_text = title_text[:37] + "..."
    draw.text((canvas_w // 2, offset_y + p_h + 90), title_text, fill="#F0F0F0", font=font_title, anchor="mm")
    
    # Precio Destacado
    draw.text((canvas_w // 2, offset_y + p_h + 200), product["price"], fill="#00FF88", font=font_price, anchor="mm")
    
    # Pie de página / Web
    draw.text((canvas_w // 2, canvas_h - 180), "cuanticopc.com.ar", fill="#CCCCCC", font=font_footer, anchor="mm")
    
    output_path = "story_preview.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path

def publish_to_instagram(image_url):
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

def process_workflow():
    product = get_product_and_image()
    image_path = create_story_template(product)
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Aprobar y Publicar", callback_data="approve"),
        InlineKeyboardButton("🔄 Probar otro", callback_data="retry")
    )
    
    caption = f"📦 *{product['name']}*\n💰 Precio: {product['price']}\n\n¿Aprobás esta imagen para Instagram Stories?"
    
    with open(image_path, "rb") as photo:
        msg = bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        
    print("Esperando la respuesta en Telegram por 120 segundos...")
    
    @bot.callback_query_handler(func=lambda call: True)
    def callback_listener(call):
        if call.data == "approve":
            bot.answer_callback_query(call.id, "Publicando en Instagram...")
            bot.edit_message_caption(chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id, caption="🚀 *Publicando en Instagram Stories...*", parse_mode="Markdown")
            
            success, result = publish_to_instagram(product["raw_url"])
            if success:
                bot.send_message(TELEGRAM_CHAT_ID, f"🎉 ¡Publicado exitosamente en Instagram! ID: `{result}`", parse_mode="Markdown")
            else:
                bot.send_message(TELEGRAM_CHAT_ID, f"❌ Error al publicar en Meta: `{result}`", parse_mode="Markdown")
            bot.stop_polling()
            
        elif call.data == "retry":
            bot.answer_callback_query(call.id, "Buscando otro producto...")
            bot.send_message(TELEGRAM_CHAT_ID, "🔄 Generando nueva opción...")
            bot.stop_polling()
            os.system("python publish_story.py")

    bot.polling(timeout=120, non_stop=False)

if __name__ == "__main__":
    process_workflow()
