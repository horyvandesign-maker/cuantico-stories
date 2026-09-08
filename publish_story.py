import os
import random
import requests
from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Configuración de variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

SITE_URL = "https://cuanticopc.com.ar"
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

def clean_image_url(url):
    base_url = url.split("?")[0]
    for ext in [".avif", ".webp", ".png", ".jpeg"]:
        if base_url.lower().endswith(ext):
            base_url = base_url[:-len(ext)] + ".jpg"
            break
    return base_url

def get_random_product():
    """Obtiene un producto y procesa sus datos."""
    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    res = requests.get(endpoint, params={"per_page": 50}, headers=headers, timeout=15)
    if res.status_code != 200 or not res.json():
        print("Error al obtener catálogo de WooCommerce.")
        exit(1)
        
    products = res.json()
    random.shuffle(products)
    
    for product in products:
        images = product.get("images", [])
        if images:
            img_url = clean_image_url(images[0].get("src", ""))
            price_raw = product.get("prices", {}).get("price", "0")
            # Convertir precio de centavos si aplica
            price = f"${int(price_raw) / 100:,.0f}".replace(",", ".") if price_raw.isdigit() else "$ Consultar"
            
            return {
                "name": product.get("name", "Producto Cuantico"),
                "price": price,
                "image_url": img_url
            }
    exit(1)

def create_story_template(product):
    """Crea una imagen de 1080x1920 con el producto encuadrado, fondo elegante y texto."""
    canvas_w, canvas_h = 1080, 1920
    
    # Descargar la imagen del producto
    res = requests.get(product["image_url"], timeout=10)
    img_orig = Image.open(BytesIO(res.content)).convert("RGB")
    
    # 1. Crear fondo con blur
    bg = img_orig.resize((canvas_w, canvas_h))
    bg = bg.filter(ImageFilter.GaussianBlur(30))
    
    # Capa oscura sobre el fondo para resaltar el producto
    overlay = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 160))
    bg.paste(overlay, (0, 0), overlay)
    
    # 2. Rescalar la imagen original manteniendo proporcion (máx 850x850)
    img_orig.thumbnail((850, 850))
    
    # Centrar la foto del producto en el lienzo
    p_w, p_h = img_orig.size
    offset_x = (canvas_w - p_w) // 2
    offset_y = (canvas_h - p_h) // 2 - 100
    bg.paste(img_orig, (offset_x, offset_y))
    
    # 3. Dibujar textos
    draw = ImageDraw.Draw(bg)
    
    # Usar fuente por defecto de Pillow
    font_large = ImageFont.load_default()
    
    # Encabezado Marca
    draw.text((canvas_w // 2, 180), "CUANTICO PC", fill="white", anchor="mm")
    
    # Nombre del Producto
    draw.text((canvas_w // 2, offset_y + p_h + 80), product["name"][:35], fill="white", anchor="mm")
    
    # Precio destacado
    draw.text((canvas_w // 2, offset_y + p_h + 160), product["price"], fill="#00FF88", anchor="mm")
    
    # Pie de página / Call to Action
    draw.text((canvas_w // 2, canvas_h - 150), "Conseguilo en cuanticopc.com.ar", fill="white", anchor="mm")
    
    # Guardar en memoria
    output_path = "story_preview.jpg"
    bg.save(output_path, "JPEG", quality=95)
    return output_path

def send_approval_request():
    product = get_random_product()
    image_path = create_story_template(product)
    
    # Crear botones de aprobación en Telegram
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("✅ Aprobar y Publicar", callback_data="approve"),
        InlineKeyboardButton("🔄 Probar otro", callback_data="retry")
    )
    
    caption = f"📦 *{product['name']}*\n💰 Precio: {product['price']}\n\n¿Aprobás esta imagen para Instagram Stories?"
    
    with open(image_path, "rb") as photo:
        bot.send_photo(TELEGRAM_CHAT_ID, photo, caption=caption, reply_markup=markup, parse_mode="Markdown")
        
    print("Previsualización enviada con éxito a Telegram.")

if __name__ == "__main__":
    send_approval_request()
