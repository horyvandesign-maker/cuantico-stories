import os
import random
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

def get_product_and_image():
    """Consulta WooCommerce, detecta si es por encargo/reserva y descarga la imagen con el precio final correcto."""
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
                
                # Validación de stock / reservas / encargo
                is_on_backorder = product.get("is_on_backorder", False)
                stock_status = product.get("stock_status", "")
                
                prices_dict = product.get("prices", {})
                
                # En wc/store/v1, prices.price contiene el valor en la unidad menor (centavos/minor units)
                # Si hay precio de oferta (sale_price), se prioriza ese sobre el precio regular.
                raw_val = prices_dict.get("price")
                
                is_on_demand = False
                
                if is_on_backorder or stock_status == "onbackorder" or not raw_val or str(raw_val) == "0":
                    is_on_demand = True
                    price = "¡DISPONIBLE POR ENCARGO!"
                else:
                    try:
                        # Extraer el valor numérico
                        val_num = int(raw_val)
                        # La API de Store usa los decimales configurados en WooCommerce (por defecto 2 decimales -> dividir por 100)
                        decimals = int(prices_dict.get("currency_minor_units", 2))
                        if decimals > 0:
                            val_final = val_num / (10 ** decimals)
                        else:
                            val_final = float(val_num)
                        
                        price = f"${val_final:,.0f}".replace(",", ".")
                    except Exception:
                        price = "¡DISPONIBLE POR ENCARGO!"
                        is_on_demand = True
                
                raw_name = clean_text(product.get("name", "Producto Cuantico"))
                ai_name = generate_ai_title(raw_name)
                
                return {
                    "name": ai_name,
                    "original_name": raw_name,
                    "price": price,
                    "is_on_demand": is_on_demand,
                    "img_obj": img_orig,
                    "raw_url": img_url
                }
        except Exception as e:
            continue

    print("No se encontró ningún producto con imagen procesable.")
    exit(1)
    
def create_story_template(product):
    """Genera la plantilla visual de 1080x1920 px con encuadre, fuentes e IA."""
    canvas_w, canvas_h = 1080, 1920
    img_orig = product["img_obj"]
    
    # 1. Fondo Oscuro con Blur
    bg = img_orig.resize((canvas_w, canvas_h))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 180))
    bg.paste(overlay, (0, 0), overlay)
    
    # 2. Rescalar y centrar la foto del producto
    img_orig.thumbnail((800, 800))
    p_w, p_h = img_orig.size
    offset_x = (canvas_w - p_w) // 2
    offset_y = (canvas_h - p_h) // 2 - 120
    bg.paste(img_orig, (offset_x, offset_y))
    
    # 3. Dibujar textos y marca
    draw = ImageDraw.Draw(bg)
    
    font_brand = get_font(50)
    font_title = get_font(44)
    font_price = get_font(65) if not product["is_on_demand"] else get_font(45)
    font_footer = get_font(38)
    
    # Encabezado
    draw.text((canvas_w // 2, 160), "CUANTICO PC", fill="#FFFFFF", font=font_brand, anchor="mm")
    
    # Título optimizado por IA en multilínea centrada
    wrapped_lines = textwrap.wrap(product["name"], width=24)
    wrapped_text = "\n".join(wrapped_lines[:3])
    
    draw.multiline_text(
        (canvas_w // 2, offset_y + p_h + 100), 
        wrapped_text, 
        fill="#F0F0F0", 
        font=font_title, 
        anchor="mm", 
        align="center"
    )
    
    # Precio o leyenda por encargo
    draw.text((canvas_w // 2, offset_y + p_h + 230), product["price"], fill="#00FF88", font=font_price, anchor="mm")
    
    # Marca de agua inferior
    draw.text((canvas_w // 2, canvas_h - 180), "cuanticopc.com.ar", fill="#CCCCCC", font=font_footer, anchor="mm")
    
    output_path = "story_preview.jpg"
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

def process_workflow():
    """Ejecuta el ciclo de creación, envío a Telegram y captura de aprobación."""
    product = get_product_and_image()
    image_path = create_story_template(product)
    
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Aprobar y Publicar", callback_data="approve"),
        InlineKeyboardButton("🔄 Probar otro", callback_data="retry")
    )
    
    caption = f"📦 *{product['original_name']}*\n💰 Precio: {product['price']}\n\n¿Aprobás esta imagen para Instagram Stories?"
    
    with open(image_path, "rb") as photo:
        msg = bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        
    print("Esperando respuesta en Telegram por 120 segundos...")
    
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
