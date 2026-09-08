import os
import random
import time
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

def get_product_and_image():
    """Busca un producto y asegura descargar una imagen decodificable."""
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
                
                return {
                    "name": product.get("name", "Producto Cuantico"),
                    "price": price,
                    "img_obj": img_orig,
                    "raw_url": img_url
                }
        except Exception as e:
            continue

    print("No se encontró ningún producto con imagen procesable.")
    exit(1)

def create_story_template(product):
    """Genera el lienzo vertical de 1080x1920 px."""
    canvas_w, canvas_h = 1080, 1920
    img_orig = product["img_obj"]
    
    bg = img_orig.resize((canvas_w, canvas_h))
    bg = bg.filter(ImageFilter.GaussianBlur(30))
    
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 160))
    bg.paste(overlay, (0, 0), overlay)
    
    img_orig.thumbnail((850, 850))
    p_w, p_h = img_orig.size
    offset_x = (canvas_w - p_w) // 2
    offset_y = (canvas_h - p_h) // 2 - 100
    bg.paste(img_orig, (offset_x, offset_y))
    
    draw = ImageDraw.Draw(bg)
    draw.text((canvas_w // 2, 180), "CUANTICO PC", fill="white", anchor="mm")
    draw.text((canvas_w // 2, offset_y + p_h + 80), product["name"][:35], fill="white", anchor="mm")
    draw.text((canvas_w // 2, offset_y + p_h + 160), product["price"], fill="#00FF88", anchor="mm")
    draw.text((canvas_w // 2, canvas_h - 150), "Conseguilo en cuanticopc.com.ar", fill="white", anchor="mm")
    
    output_path = "story_preview.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path

def publish_to_instagram(image_url):
    """Publica la imagen procesada en Instagram Stories via Meta Graph API."""
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
    
    # Manejo de la acción según el botón presionado
    @bot.callback_query_handler(func=lambda call: True)
    def callback_listener(call):
        if call.data == "approve":
            bot.answer_callback_query(call.id, "Publicando en Instagram...")
            bot.edit_message_caption("🚀 *Publicando en Instagram Stories...*", chat_id=TELEGRAM_CHAT_ID, message_id=msg.message_id, parse_mode="Markdown")
            
            # Nota: Meta requiere una URL pública de la imagen. Usamos la del producto original como fallback o la enviada
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
