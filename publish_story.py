import html
import os
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import requests
import telebot

# ------------------------------------------------------------------------------
# CONFIGURACIÓN Y VARIABLES DE ENTORNO
# ------------------------------------------------------------------------------
WC_URL = os.getenv("WC_URL", "https://cuanticopc.com.ar")
WC_CONSUMER_KEY = os.getenv("WC_CONSUMER_KEY")
WC_CONSUMER_SECRET = os.getenv("WC_CONSUMER_SECRET")

INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None


# ------------------------------------------------------------------------------
# 1. OBTENER PRODUCTOS DE WOOCOMMERCE
# ------------------------------------------------------------------------------
def get_products():
    """Obtiene los productos publicados de la tienda WooCommerce."""
    endpoint = f"{WC_URL.rstrip('/')}/wp-json/wc/v3/products"
    params = {
        "status": "publish",
        "per_page": 100,
        "consumer_key": WC_CONSUMER_KEY,
        "consumer_secret": WC_CONSUMER_SECRET,
    }
    try:
        response = requests.get(endpoint, params=params, timeout=15)
        response.raise_for_status()
        raw_products = response.json()

        products = []
        for p in raw_products:
            if not p.get("images"):
                continue

            # Formatear precio o marcar como encargue
            raw_price = p.get("price")
            is_on_demand = not raw_price or float(raw_price) == 0

            price_str = (
                f"${float(raw_price):,.0f} ARS".replace(",", ".")
                if not is_on_demand
                else "POR ENCARGUE"
            )

            products.append(
                {
                    "id": p["id"],
                    "original_name": p["name"],
                    "ai_name": p["name"],  # Se puede integrar con IA si se desea
                    "permalink": p["permalink"],
                    "image_url": p["images"][0]["src"],
                    "price": price_str,
                    "is_on_demand": is_on_demand,
                }
            )

        return products
    except Exception as err:
        print(f"Error obteniendo productos de WooCommerce: {err}")
        return []


# ------------------------------------------------------------------------------
# 2. GENERAR IMAGEN CYBERPUNK CON PILLOW
# ------------------------------------------------------------------------------
def generate_story_image(product):
    """Genera la imagen 1080x1920 con el diseño Cyberpunk y el CTA único."""
    width, height = 1080, 1920

    # Fondo base oscuro
    bg = Image.new("RGBA", (width, height), (12, 12, 20, 255))
    draw = ImageDraw.Draw(bg)

    # Cargar Fuentes
    try:
        font_title = ImageFont.truetype("arial.ttf", 40)
        font_price = ImageFont.truetype("arial.ttf", 44)
        font_cta = ImageFont.truetype("arial.ttf", 36)
    except IOError:
        font_title = font_price = font_cta = ImageFont.load_default()

    # Descargar e incrustar imagen del producto
    temp_img_path = f"temp_{product['id']}.jpg"
    try:
        res = requests.get(product["image_url"], stream=True, timeout=15)
        if res.status_code == 200:
            with open(temp_img_path, "wb") as f:
                for chunk in res.iter_content(1024):
                    f.write(chunk)

            prod_img = Image.open(temp_img_path).convert("RGBA")
            prod_img.thumbnail((750, 750))

            # Contenedor Blanco Central con Borde Rosa/Cian
            card_x1, card_y1 = 110, 360
            card_x2, card_y2 = 970, 1220

            # Marco Neón exterior
            draw.rectangle(
                [card_x1 - 4, card_y1 - 4, card_x2 + 4, card_y2 + 4],
                fill=(255, 0, 128, 100),
            )
            draw.rectangle(
                [card_x1, card_y1, card_x2, card_y2],
                fill=(255, 255, 255, 255),
                outline=(0, 240, 255),
                width=4,
            )

            # Centrar la foto en el contenedor
            px = card_x1 + (860 - prod_img.width) // 2
            py = card_y1 + (860 - prod_img.height) // 2
            bg.paste(prod_img, (px, py), prod_img)
    except Exception as err:
        print(f"Error procesando la imagen del producto: {err}")
    finally:
        if os.path.exists(temp_img_path):
            os.remove(temp_img_path)

    # Título del Producto (Arriba del precio)
    title_text = product.get("ai_name", product["original_name"]).upper()
    if len(title_text) > 45:
        title_text = title_text[:42] + "..."

    draw.text(
        (540, 1280),
        title_text,
        fill="#FFFFFF",
        font=font_title,
        anchor="mm",
    )

    # Badge de Precio / Estado
    price_text = (
        product["price"]
        if not product["is_on_demand"]
        else ">> PRODUCTO POR ENCARGUE <<"
    )
    draw.rectangle(
        [180, 1360, 900, 1450],
        fill=(20, 20, 30, 230),
        outline="#FF007F",
        width=2,
    )
    draw.text(
        (540, 1405),
        price_text,
        fill="#FF007F",
        font=font_price,
        anchor="mm",
    )

    # BANNER ÚNICO CTA (RESPONDÉ 'INFO' PARA COMPRAR)
    cta_text = "💬 RESPONDÉ 'INFO' PARA COMPRAR"
    cta_w, cta_h = 840, 110
    cta_x1 = (width - cta_w) // 2
    cta_y1 = 1560

    draw.rectangle(
        [cta_x1, cta_y1, cta_x1 + cta_w, cta_y1 + cta_h],
        fill=(10, 15, 25, 245),
        outline="#00F0FF",
        width=4,
    )

    draw.text(
        (540, cta_y1 + (cta_h // 2)),
        cta_text,
        fill="#00F0FF",
        font=font_cta,
        anchor="mm",
    )

    # Guardar Resultado
    output_path = f"story_{product['id']}.jpg"
    final_image = bg.convert("RGB")
    final_image.save(output_path, "JPEG", quality=95, optimize=True)

    return output_path


# ------------------------------------------------------------------------------
# 3. PUBLICAR EN INSTAGRAM GRAPH API
# ------------------------------------------------------------------------------
def publish_to_instagram(image_path, permalink):
    """Sube la imagen a Instagram Stories mediante la Graph API."""
    try:
        # En GitHub Actions se requiere servir la imagen temporalmente o usar un bucket/URL accesible.
        # Asumiendo endpoint activo de carga:
        container_url = (
            f"https://graph.facebook.com/v18.0/{INSTAGRAM_ACCOUNT_ID}/media"
        )
        payload = {
            "media_type": "STORIES",
            "image_url": f"https://raw.githubusercontent.com/{os.getenv('GITHUB_REPOSITORY')}/main/{image_path}",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }

        r = requests.post(container_url, data=payload, timeout=30)
        res_data = r.json()

        if "id" not in res_data:
            return False, f"Error creando contenedor: {res_data}"

        creation_id = res_data["id"]

        # Publicar contenedor
        publish_url = f"https://graph.facebook.com/v18.0/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        pub_payload = {
            "creation_id": creation_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }

        r_pub = requests.post(publish_url, data=pub_payload, timeout=30)
        pub_data = r_pub.json()

        if "id" in pub_data:
            return True, pub_data["id"]
        return False, f"Error publicando contenedor: {pub_data}"

    except Exception as err:
        return False, str(err)


def delete_local_file(path):
    if os.path.exists(path):
        os.remove(path)


# ------------------------------------------------------------------------------
# 4. FLUJO PRINCIPAL Y NOTIFICACIONES
# ------------------------------------------------------------------------------
def process_catalog(auto_approve=True):
    products = get_products()
    if not products:
        print("No se encontraron productos en la tienda.")
        return

    # Algoritmo de rotación cíclica según el día/hora del año
    cycle_index = int(datetime.now().timestamp() // 28800) % len(products)
    product = products[cycle_index]

    print(f"Procesando producto: {product['original_name']}")
    image_path = generate_story_image(product)

    if auto_approve:
        success, result = publish_to_instagram(
            image_path, product["permalink"]
        )

        if success:
            print("Publicado con éxito en Instagram.")

            # ENVÍO DE NOTIFICACIÓN CON FOTO A TELEGRAM
            if bot and TELEGRAM_CHAT_ID:
                try:
                    escaped_name = html.escape(product["original_name"])
                    escaped_permalink = html.escape(
                        product["permalink"], quote=True
                    )
                    type_str = (
                        "📦 POR ENCARGUE"
                        if product["is_on_demand"]
                        else f"💰 {product['price']}"
                    )

                    caption = (
                        "🎉 <b>¡Story publicada con éxito!</b>\n\n"
                        f"📦 <b>{escaped_name}</b>\n"
                        f"Estado: <b>{type_str}</b>\n\n"
                        f'🔗 <a href="{escaped_permalink}">Ver en la tienda web</a>'
                    )

                    with open(image_path, "rb") as photo_file:
                        bot.send_photo(
                            TELEGRAM_CHAT_ID,
                            photo=photo_file,
                            caption=caption,
                            parse_mode="HTML",
                        )
                except Exception as err:
                    print(f"Error enviando foto a Telegram: {err}")

        else:
            print(f"Error publicando en Instagram: {result}")
            if bot and TELEGRAM_CHAT_ID:
                try:
                    bot.send_message(
                        TELEGRAM_CHAT_ID,
                        f"❌ <b>Error al publicar en Instagram:</b>\n<code>{html.escape(str(result))}</code>",
                        parse_mode="HTML",
                    )
                except Exception as err:
                    print(f"Error enviando error a Telegram: {err}")

        # Se borra el archivo local LUEGO de haber sido enviado por Telegram
        delete_local_file(image_path)


if __name__ == "__main__":
    process_catalog(auto_approve=True)
