# ============================================================
# 11/09 - ambos botones publican y muestran la imagen q se va a publicar
# ============================================================

import os
import time
import html
import json
import textwrap
import random
import math
import requests

from io import BytesIO
from PIL import Image, ImageFilter, ImageDraw, ImageFont

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from google import genai

# ============================================================
# CONFIGURACIÓN
# ============================================================

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Opcional.
# Si no está configurado se usa tmpfiles.org como fallback.
FREEIMAGE_API_KEY = os.environ.get("FREEIMAGE_API_KEY")

# Permite cambiar la versión desde GitHub Secrets/Variables
META_API_VERSION = os.environ.get("META_API_VERSION", "v26.0")

SITE_URL = "https://cuanticopc.com.ar"
HISTORY_FILE = "published_history.json"

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None


# ============================================================
# COLORES
# ============================================================

ACCENT_COLORS = [
    "#00FF88",
    "#00E5FF",
    "#B000FF",
    "#FF2BD6",
    "#FF3D71",
    "#FF6B35",
    "#FFB703",
    "#FFD60A",
    "#39FF14",
    "#00F5D4",
    "#00BBF9",
    "#4361EE",
    "#7209B7",
    "#F72585",
    "#FB5607",
    "#8338EC",
    "#3A86FF",
    "#06D6A0",
    "#EF476F",
    "#118AB2",
    "#9B5DE5",
    "#F15BB5",
    "#FEE440",
    "#00F5D4",
]

_color_bag = []
_last_accent = None


def reset_color_bag():
    global _color_bag
    _color_bag = list(dict.fromkeys(ACCENT_COLORS))
    random.shuffle(_color_bag)


def get_next_accent():
    global _color_bag
    global _last_accent

    if not _color_bag:
        reset_color_bag()
        if (
            _last_accent
            and len(_color_bag) > 1
            and _color_bag[-1] == _last_accent
        ):
            _color_bag[0], _color_bag[-1] = (
                _color_bag[-1],
                _color_bag[0],
            )

    color = _color_bag.pop()

    if color == _last_accent and _color_bag:
        alternative = _color_bag.pop()
        _color_bag.append(color)
        color = alternative

    _last_accent = color
    return color


reset_color_bag()


# ============================================================
# ESTADO DEL BOT
# ============================================================

user_choice = {
    "action": None
}


# ============================================================
# HISTORIAL
# ============================================================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as file:
            history = json.load(file)

        if isinstance(history, list):
            return history
    except Exception as error:
        print(f"No se pudo leer historial: {error}")

    return []


def save_to_history(product_id):
    history = load_history()

    if product_id not in history:
        history.append(product_id)

    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as file:
            json.dump(
                history[-200:],
                file,
                ensure_ascii=False,
                indent=2,
            )
    except Exception as error:
        print(f"No se pudo guardar historial: {error}")


# ============================================================
# TELEGRAM
# ============================================================

def register_telegram_handlers():
    if not bot:
        return

    @bot.callback_query_handler(func=lambda call: True)
    def global_callback_listener(call):
        try:
            if call.data.startswith("approve_"):
                user_choice["action"] = "approve"
                bot.answer_callback_query(call.id, "Publicando...")
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=(
                        "🚀 <b>Publicando diseño final "
                        "en Instagram Stories...</b>"
                    ),
                    parse_mode="HTML",
                )

            elif call.data.startswith("skip_"):
                user_choice["action"] = "skip"
                bot.answer_callback_query(call.id, "Salteado.")
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption="⏭️ <b>Producto salteado.</b>",
                    parse_mode="HTML",
                )

            elif call.data == "stop":
                user_choice["action"] = "stop"
                bot.answer_callback_query(call.id, "Deteniendo proceso...")
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption="🛑 <b>Proceso detenido.</b>",
                    parse_mode="HTML",
                )

        except Exception as error:
            print(f"Error callback Telegram: {error}")

        finally:
            try:
                bot.stop_polling()
            except Exception:
                pass


register_telegram_handlers()


# ============================================================
# FUENTES Y TEXTO
# ============================================================

def get_font(size):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]

    for font_path in paths:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass

    return ImageFont.load_default()


FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")


def get_display_font(size):
    """Fuente de impacto para el titulo (condensada, tipo afiche)."""
    candidates = [
        os.path.join(FONT_DIR, "BebasNeue-Bold.otf"),
        "/usr/share/fonts/opentype/bebas-neue/BebasNeue-Bold.otf",
        "/usr/share/fonts/truetype/bebas-neue/BebasNeue-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return get_font(int(size * 0.8))


def get_heading_font(size):
    """Fuente para badges, CTA y textos de apoyo."""
    candidates = [
        os.path.join(FONT_DIR, "LeagueSpartan-Bold.otf"),
        "/usr/share/fonts/opentype/league-spartan/LeagueSpartan-Bold.otf",
        "/usr/share/fonts/truetype/league-spartan/LeagueSpartan-Bold.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return get_font(size)


def get_contrast_text_color(rgb):
    luminance = (0.299 * rgb[0]) + (0.587 * rgb[1]) + (0.114 * rgb[2])
    return "#0A0C12" if luminance > 150 else "#FFFFFF"


def draw_sparkle(layer, x, y, color_rgb, size=20):
    glow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (x - size * 1.8, y - size * 1.8, x + size * 1.8, y + size * 1.8),
        fill=(color_rgb[0], color_rgb[1], color_rgb[2], 100),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(9))
    layer.alpha_composite(glow)

    draw = ImageDraw.Draw(layer)
    points = [
        (x, y - size), (x + size * 0.22, y - size * 0.22),
        (x + size, y), (x + size * 0.22, y + size * 0.22),
        (x, y + size), (x - size * 0.22, y + size * 0.22),
        (x - size, y), (x - size * 0.22, y - size * 0.22),
    ]
    draw.polygon(points, fill=(255, 255, 255, 235))

    small = size * 0.4
    sx, sy = x + size * 1.35, y - size * 0.9
    small_points = [
        (sx, sy - small), (sx + small * 0.22, sy - small * 0.22),
        (sx + small, sy), (sx + small * 0.22, sy + small * 0.22),
        (sx, sy + small), (sx - small * 0.22, sy + small * 0.22),
        (sx - small, sy), (sx - small * 0.22, sy - small * 0.22),
    ]
    draw.polygon(small_points, fill=(color_rgb[0], color_rgb[1], color_rgb[2], 220))


def draw_chat_icon(layer, cx, cy, color_rgb, radius=24):
    draw = ImageDraw.Draw(layer)
    bubble_w = radius * 2.2
    bubble_h = radius * 1.7
    x1 = cx - bubble_w / 2
    y1 = cy - bubble_h / 2 - 4
    x2 = cx + bubble_w / 2
    y2 = cy + bubble_h / 2 - 4

    draw.rounded_rectangle(
        (x1, y1, x2, y2), radius=10,
        fill=(color_rgb[0], color_rgb[1], color_rgb[2], 255),
    )
    tail = [
        (cx - bubble_w * 0.18, y2 - 1),
        (cx - bubble_w * 0.18, y2 + 11),
        (cx + bubble_w * 0.06, y2 - 1),
    ]
    draw.polygon(tail, fill=(color_rgb[0], color_rgb[1], color_rgb[2], 255))

    dot_r = 2.8
    spacing = 10
    dot_cy = (y1 + y2) / 2
    for i in range(-1, 2):
        ddx = cx + i * spacing
        draw.ellipse(
            (ddx - dot_r, dot_cy - dot_r, ddx + dot_r, dot_cy + dot_r),
            fill=(10, 12, 18, 255),
        )



def clean_text(text):
    if not text:
        return ""

    decoded = html.unescape(str(text))
    return (
        decoded
        .replace('"', "'")
        .replace("”", "'")
        .replace("“", "'")
        .strip()
    )


def hex_to_rgb(hex_string):
    hex_string = hex_string.lstrip("#")
    return tuple(
        int(hex_string[i:i + 2], 16)
        for i in (0, 2, 4)
    )


def random_secondary_color(primary_hex):
    available = [color for color in ACCENT_COLORS if color != primary_hex]
    return random.choice(available)


# ============================================================
# UTILIDADES DE DIBUJO
# ============================================================

def draw_neon_glow_line(layer, points, color_rgb, width=5, glow_intensity=4):
    glow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)

    for level in range(glow_intensity, 0, -1):
        glow_width = width + (level * 6)
        glow_draw.line(
            points,
            fill=(color_rgb[0], color_rgb[1], color_rgb[2], 80),
            width=glow_width,
            joint="curve",
        )

    glow = glow.filter(ImageFilter.GaussianBlur(8))
    layer.alpha_composite(glow)

    draw = ImageDraw.Draw(layer)
    draw.line(
        points,
        fill=(color_rgb[0], color_rgb[1], color_rgb[2], 235),
        width=width,
        joint="curve",
    )


def draw_glowing_node(layer, x, y, color_rgb, radius=7):
    glow = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_radius = radius * 4

    glow_draw.ellipse(
        (x - glow_radius, y - glow_radius, x + glow_radius, y + glow_radius),
        fill=(color_rgb[0], color_rgb[1], color_rgb[2], 100),
    )

    glow = glow.filter(ImageFilter.GaussianBlur(radius * 2))
    layer.alpha_composite(glow)

    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        (x - radius, y - radius, x + radius, y + radius),
        fill=(255, 255, 255, 245),
        outline=(color_rgb[0], color_rgb[1], color_rgb[2], 255),
        width=2,
    )


def draw_random_circuit(layer, start_x, start_y, direction, color_rgb):
    x, y = start_x, start_y
    points = [(x, y)]
    segments = random.randint(2, 5)

    for _ in range(segments):
        horizontal = random.randint(70, 190) * direction
        x += horizontal
        points.append((x, y))

        vertical = random.choice([-1, 1]) * random.randint(40, 130)
        y += vertical
        points.append((x, y))

    width = random.randint(2, 6)
    draw_neon_glow_line(
        layer,
        points,
        color_rgb,
        width=width,
        glow_intensity=random.randint(2, 4),
    )

    if random.random() < 0.8:
        draw_glowing_node(layer, x, y, color_rgb, radius=random.randint(4, 9))


def draw_random_particles(layer, color_rgb, secondary_rgb, count=20):
    draw = ImageDraw.Draw(layer)
    canvas_w, canvas_h = layer.size

    for _ in range(count):
        area = random.choice(["top", "bottom", "left", "right"])

        if area == "top":
            x, y = random.randint(20, canvas_w - 20), random.randint(120, 380)
        elif area == "bottom":
            x, y = random.randint(20, canvas_w - 20), random.randint(1500, 1800)
        elif area == "left":
            x, y = random.randint(10, 150), random.randint(350, 1500)
        else:
            x, y = random.randint(canvas_w - 150, canvas_w - 10), random.randint(350, 1500)

        radius = random.randint(2, 6)
        rgb = random.choice([color_rgb, secondary_rgb])
        alpha = random.randint(60, 180)

        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(rgb[0], rgb[1], rgb[2], alpha),
        )


def draw_random_rings(layer, color_rgb, secondary_rgb):
    draw = ImageDraw.Draw(layer)
    canvas_w, canvas_h = layer.size

    for _ in range(random.randint(2, 5)):
        side = random.choice(["left", "right", "top", "bottom"])
        radius = random.randint(60, 180)

        if side == "left":
            cx, cy = random.randint(-50, 100), random.randint(300, 1600)
        elif side == "right":
            cx, cy = random.randint(canvas_w - 100, canvas_w + 50), random.randint(300, 1600)
        elif side == "top":
            cx, cy = random.randint(100, canvas_w - 100), random.randint(100, 260)
        else:
            cx, cy = random.randint(100, canvas_w - 100), random.randint(1550, 1800)

        rgb = random.choice([color_rgb, secondary_rgb])
        draw.arc(
            (cx - radius, cy - radius, cx + radius, cy + radius),
            start=random.randint(0, 120),
            end=random.randint(220, 350),
            fill=(rgb[0], rgb[1], rgb[2], random.randint(70, 180)),
            width=random.randint(2, 5),
        )


def draw_random_triangles(layer, color_rgb, secondary_rgb):
    draw = ImageDraw.Draw(layer)
    canvas_w, canvas_h = layer.size

    for _ in range(random.randint(1, 4)):
        side = random.choice(["left", "right"])
        center_x = random.randint(30, 130) if side == "left" else random.randint(canvas_w - 130, canvas_w - 30)
        center_y = random.randint(350, 1550)
        size = random.randint(35, 90)
        rotation = random.random() * math.pi

        points = []
        for n in range(3):
            angle = rotation + (2 * math.pi * n / 3)
            px = center_x + (math.cos(angle) * size)
            py = center_y + (math.sin(angle) * size)
            points.append((px, py))

        rgb = random.choice([color_rgb, secondary_rgb])
        draw.line(
            points + [points[0]],
            fill=(rgb[0], rgb[1], rgb[2], random.randint(80, 180)),
            width=random.randint(2, 4),
        )


def create_random_tech_layer(canvas_w, canvas_h, accent_rgb, secondary_rgb):
    layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    for _ in range(random.randint(1, 3)):
        draw_random_circuit(layer, random.randint(-100, 80), random.randint(220, 1500), 1, random.choice([accent_rgb, secondary_rgb]))

    for _ in range(random.randint(1, 3)):
        draw_random_circuit(layer, random.randint(canvas_w - 80, canvas_w + 100), random.randint(220, 1500), -1, random.choice([accent_rgb, secondary_rgb]))

    draw_random_particles(layer, accent_rgb, secondary_rgb, count=random.randint(12, 30))

    if random.random() < 0.8:
        draw_random_rings(layer, accent_rgb, secondary_rgb)

    if random.random() < 0.7:
        draw_random_triangles(layer, accent_rgb, secondary_rgb)

    return layer


# ============================================================
# GEMINI & WOOCOMMERCE
# ============================================================

def generate_ai_title(original_title, permalink=""):
    if not GEMINI_API_KEY:
        return original_title

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = (
            "Analizá este producto tecnológico:\n"
            f"{original_title}\n\n"
            "Creá un título comercial para una Instagram Story.\n\n"
            "REGLAS OBLIGATORIAS:\n"
            "- Español latino.\n"
            "- Máximo 6 palabras.\n"
            "- Sin emojis.\n"
            "- Sin comillas.\n"
            "- Directo y comercial.\n"
            "- No inventes especificaciones.\n"
            "- Conservá el tipo de producto.\n"
        )
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        ai_text = clean_text(response.text)
        if len(ai_text) > 3:
            return ai_text
    except Exception as error:
        print(f"Fallback título original: {error}")

    return original_title


def fetch_all_catalog_products():
    from datetime import datetime

    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
    }

    catalog = []
    page = 1

    while True:
        params = {"per_page": 50, "page": page, "_nocache": int(time.time())}
        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=20)
        except requests.RequestException as error:
            print(f"Error WooCommerce: {error}")
            break

        if response.status_code != 200:
            break

        try:
            items = response.json()
        except Exception:
            break

        if not items:
            break

        for product in items:
            images = product.get("images", [])
            if not images:
                continue

            raw_image_url = images[0].get("src", "")
            if not raw_image_url:
                continue

            prices_info = product.get("prices", {})
            raw_price = prices_info.get("price")

            is_in_stock = product.get("is_in_stock", True)
            is_on_backorder = product.get("is_on_backorder", False)
            is_purchasable = product.get("is_purchasable", True)

            price_val = 0
            if raw_price is not None and str(raw_price).strip():
                try:
                    price_val = int(raw_price)
                except (ValueError, TypeError):
                    price_val = 0

            if not is_in_stock or is_on_backorder or not is_purchasable or price_val <= 0:
                is_on_demand = True
                formatted_price = "POR ENCARGUE"
            else:
                is_on_demand = False
                val_final = price_val / 100
                formatted_price = f"${val_final:,.0f}".replace(",", ".")

            catalog.append({
                "id": product.get("id"),
                "original_name": clean_text(product.get("name", "Producto Cuantico")),
                "price": formatted_price,
                "is_on_demand": is_on_demand,
                "raw_url": raw_image_url,
                "permalink": product.get("permalink", SITE_URL),
            })

        page += 1

    if not catalog:
        return []

    now = datetime.now()
    run_index = (now.toordinal() * 2 + (0 if now.hour < 14 else 1)) % len(catalog)
    selected_product = catalog[run_index]

    print(f"Producto seleccionado por rotación: {selected_product['original_name']}")
    return [selected_product]


# ============================================================
# CREACIÓN DE STORY (TÍTULO ARRIBA, BORDES GRUESOS Y NEÓN POTENCIADO)
# ============================================================

def create_story_template(product, img_obj):
    canvas_w = 1080
    canvas_h = 1920

    accent_hex = get_next_accent()
    secondary_hex = random_secondary_color(accent_hex)
    accent_rgb = hex_to_rgb(accent_hex)
    secondary_rgb = hex_to_rgb(secondary_hex)

    print(f"Story {product['id']} color={accent_hex} secundario={secondary_hex}")

    background_source = img_obj.convert("RGB").resize((canvas_w, canvas_h))
    background_source = background_source.filter(ImageFilter.GaussianBlur(random.randint(65, 95))).convert("RGBA")

    darkness = random.randint(205, 225)
    dark_overlay = Image.new(
        "RGBA",
        (canvas_w, canvas_h),
        (random.randint(5, 10), random.randint(6, 12), random.randint(12, 20), darkness),
    )
    background_source.alpha_composite(dark_overlay)
    bg = background_source

    texture_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    tex_draw = ImageDraw.Draw(texture_layer)
    for x in range(0, canvas_w, 35):
        for y in range(0, canvas_h, 35):
            tex_draw.ellipse((x, y, x + 2, y + 2), fill=(255, 255, 255, 55))
    bg.alpha_composite(texture_layer)

    atmospheric_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(atmospheric_glow)
    glow_x, glow_y, glow_radius = random.randint(250, 830), random.randint(600, 1250), random.randint(350, 550)
    glow_draw.ellipse(
        (glow_x - glow_radius, glow_y - glow_radius, glow_x + glow_radius, glow_y + glow_radius),
        fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], random.randint(40, 75)),
    )
    atmospheric_glow = atmospheric_glow.filter(ImageFilter.GaussianBlur(130))
    bg.alpha_composite(atmospheric_glow)

    tech_layer = create_random_tech_layer(canvas_w, canvas_h, accent_rgb, secondary_rgb)
    bg.alpha_composite(tech_layer)

    draw = ImageDraw.Draw(bg)

    logo_path = os.path.join(os.path.dirname(__file__), "logo_canva.png")
    logo_h_space = 140
    has_logo = False
    if os.path.exists(logo_path):
        try:
            logo_img = Image.open(logo_path).convert("RGBA")
            logo_img.thumbnail((450, 150), Image.Resampling.LANCZOS)
            logo_w, logo_h = logo_img.size
            bg.paste(logo_img, ((canvas_w - logo_w) // 2, 90), logo_img)
            logo_h_space = 90 + logo_h + 25
            has_logo = True
        except Exception as error:
            print(f"Error logo: {error}")

    if not has_logo:
        draw.text((canvas_w // 2, 120), "CUANTICO PC", fill="#FFFFFF", font=get_heading_font(45), anchor="mm")
        logo_h_space = 160

    font_title = get_display_font(66)
    ai_name = product.get("ai_name", product["original_name"]).upper()
    wrapped_lines = textwrap.wrap(ai_name, width=24)[:2]
    wrapped_text = "\n".join(wrapped_lines)
    title_y = logo_h_space + 25
    line_height = 62

    draw.multiline_text(
        (canvas_w // 2 + 3, title_y + 3), wrapped_text, fill=(0, 0, 0, 230),
        font=font_title, anchor="mm", align="center", spacing=6,
    )
    draw.multiline_text(
        (canvas_w // 2, title_y), wrapped_text, fill="#FFFFFF",
        font=font_title, anchor="mm", align="center", spacing=6,
    )

    underline_y = title_y + ((len(wrapped_lines) * line_height) // 2) + 22
    underline_half = 120
    draw_neon_glow_line(
        bg,
        [(canvas_w // 2 - underline_half, underline_y), (canvas_w // 2 + underline_half, underline_y)],
        accent_rgb, width=5, glow_intensity=3,
    )

    card_w = 860
    card_h = 860
    card_x = (canvas_w - card_w) // 2
    card_y = underline_y + 40

    inner_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    ig_draw = ImageDraw.Draw(inner_glow)
    ig_draw.ellipse(
        (card_x + card_w * 0.08, card_y + card_h * 0.08, card_x + card_w * 0.92, card_y + card_h * 0.92),
        fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 55),
    )
    inner_glow = inner_glow.filter(ImageFilter.GaussianBlur(95))
    bg.alpha_composite(inner_glow)

    glass_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    glass_draw = ImageDraw.Draw(glass_layer)
    glass_draw.rounded_rectangle(
        (card_x, card_y, card_x + card_w, card_y + card_h), radius=42, fill=(255, 255, 255, 12),
    )
    bg.alpha_composite(glass_layer)

    card_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    cg_draw = ImageDraw.Draw(card_glow)
    cg_draw.rounded_rectangle(
        (card_x - 18, card_y - 18, card_x + card_w + 18, card_y + card_h + 18),
        radius=48, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 180),
    )
    card_glow = card_glow.filter(ImageFilter.GaussianBlur(24))
    bg.alpha_composite(card_glow)

    draw = ImageDraw.Draw(bg)
    draw.rounded_rectangle(
        (card_x, card_y, card_x + card_w, card_y + card_h), radius=38, outline=accent_hex, width=6,
    )

    shadow_layer = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(shadow_layer)
    sh_cx, sh_cy = card_x + card_w // 2, card_y + card_h - 90
    sh_draw.ellipse((sh_cx - 260, sh_cy - 45, sh_cx + 260, sh_cy + 45), fill=(0, 0, 0, 150))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(35))
    bg.alpha_composite(shadow_layer)

    img_copy = img_obj.copy().convert("RGBA")
    max_product_size = 700
    img_copy.thumbnail((max_product_size, max_product_size), Image.Resampling.LANCZOS)
    product_w, product_h = img_copy.size
    product_x = card_x + (card_w - product_w) // 2
    product_y = card_y + (card_h - product_h) // 2
    bg.paste(img_copy, (product_x, product_y), img_copy)

    draw = ImageDraw.Draw(bg)

    draw_sparkle(bg, card_x + card_w - 4, card_y + 8, accent_rgb, size=22)
    draw_sparkle(bg, card_x + 10, card_y + card_h - 2, secondary_rgb, size=15)

    display_label = "POR ENCARGUE" if product["is_on_demand"] else f'{product["price"]} ARS'
    badge_font_size = 34 if product["is_on_demand"] else 44
    font_badge = get_heading_font(badge_font_size)

    bbox = draw.textbbox((0, 0), display_label, font=font_badge)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    badge_w = min(text_w + 100, 920)
    badge_h = text_h + 48

    badge_x1 = (canvas_w - badge_w) // 2
    badge_y1 = card_y + card_h - (badge_h // 2)
    badge_x2 = badge_x1 + badge_w
    badge_y2 = badge_y1 + badge_h

    badge_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    bgd = ImageDraw.Draw(badge_glow)
    bgd.rounded_rectangle(
        (badge_x1 - 10, badge_y1 - 10, badge_x2 + 10, badge_y2 + 10),
        radius=24, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 190),
    )
    badge_glow = badge_glow.filter(ImageFilter.GaussianBlur(18))
    bg.alpha_composite(badge_glow)

    draw = ImageDraw.Draw(bg)
    badge_text_color = get_contrast_text_color(accent_rgb)

    if product["is_on_demand"]:
        draw.rounded_rectangle(
            (badge_x1, badge_y1, badge_x2, badge_y2), radius=24,
            fill=(10, 12, 18, 250), outline=accent_hex, width=6,
        )
        badge_text_color = "#FFFFFF"
    else:
        cut = 20
        poly_points = [
            (badge_x1 + cut, badge_y1), (badge_x2 - cut, badge_y1),
            (badge_x2, badge_y1 + cut), (badge_x2, badge_y2 - cut),
            (badge_x2 - cut, badge_y2), (badge_x1 + cut, badge_y2),
            (badge_x1, badge_y2 - cut), (badge_x1, badge_y1 + cut),
        ]
        draw.polygon(poly_points, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 255))
        draw.line(poly_points + [poly_points[0]], fill=(255, 255, 255, 235), width=4, joint="curve")

    draw.text(
        ((badge_x1 + badge_x2) // 2, (badge_y1 + badge_y2) // 2 - 2),
        display_label, fill=badge_text_color, font=font_badge, anchor="mm",
    )

    if product["is_on_demand"]:
        cta_options = [
            "Respondé 'QUIERO' por DM para encargarlo",
            "Mandá 'QUIERO' por DM y te asesoramos",
            "Escribinos 'QUIERO' y lo traemos para vos",
        ]
    else:
        cta_options = [
            "Respondé 'INFO' para comprar",
            "Comentá 'QUIERO' por DM para comprar",
            "Mandá 'LINK' por DM y conseguilo hoy",
            "Respondé 'INFO' para enviarte la oferta",
        ]

    cta_text = random.choice(cta_options)
    font_cta = get_heading_font(32)

    bbox_cta = draw.textbbox((0, 0), cta_text, font=font_cta)
    cta_text_w = bbox_cta[2] - bbox_cta[0]

    icon_radius = 26
    icon_gap = 18
    group_w = (icon_radius * 2) + icon_gap + cta_text_w
    cta_box_w = min(group_w + 110, 980)
    cta_box_h = 96
    cta_x1 = (canvas_w - cta_box_w) // 2
    cta_y1 = canvas_h - 260
    cta_x2 = cta_x1 + cta_box_w
    cta_y2 = cta_y1 + cta_box_h

    cta_glow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    cta_glow_draw = ImageDraw.Draw(cta_glow)
    cta_glow_draw.rounded_rectangle(
        (cta_x1 - 12, cta_y1 - 12, cta_x2 + 12, cta_y2 + 12),
        radius=28, fill=(accent_rgb[0], accent_rgb[1], accent_rgb[2], 190),
    )
    cta_glow = cta_glow.filter(ImageFilter.GaussianBlur(18))
    bg.alpha_composite(cta_glow)

    draw = ImageDraw.Draw(bg)
    draw.rounded_rectangle(
        (cta_x1, cta_y1, cta_x2, cta_y2), radius=20,
        fill=(10, 12, 18, 248), outline=accent_hex, width=6,
    )

    group_x1 = canvas_w // 2 - group_w // 2
    icon_cx = group_x1 + icon_radius
    icon_cy = (cta_y1 + cta_y2) // 2
    text_x = icon_cx + icon_radius + icon_gap

    draw_chat_icon(bg, icon_cx, icon_cy, accent_rgb, radius=icon_radius)
    draw.text((text_x, icon_cy), cta_text, fill="#FFFFFF", font=font_cta, anchor="lm")

    output_path = f"story_{product['id']}.jpg"
    final_image = bg.convert("RGB")
    final_image.save(output_path, "JPEG", quality=95, optimize=True)
    return output_path


# ============================================================
# SUBIDA TEMPORAL DE IMAGEN
# ============================================================

def upload_local_image_to_web(local_filepath):
    if FREEIMAGE_API_KEY:
        try:
            with open(local_filepath, "rb") as file:
                response = requests.post(
                    "https://freeimage.host/api/1/upload",
                    data={"key": FREEIMAGE_API_KEY, "action": "upload", "format": "json"},
                    files={"source": file},
                    timeout=30,
                )
            data = response.json()
            if response.status_code == 200 and "image" in data and "url" in data["image"]:
                return data["image"]["url"]
        except Exception as error:
            print(f"Error FreeImage: {error}")

    try:
        with open(local_filepath, "rb") as file:
            response = requests.post("https://tmpfiles.org/api/v1/upload", files={"file": file}, timeout=30)
        data = response.json()
        if "data" in data and "url" in data["data"]:
            url = data["data"]["url"]
            return url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
    except Exception as error:
        print(f"Error tmpfiles: {error}")

    return None


# ============================================================
# INSTAGRAM
# ============================================================

def wait_for_container(container_id, timeout_seconds=60):
    status_url = f"https://graph.facebook.com/{META_API_VERSION}/{container_id}"
    started = time.time()

    while time.time() - started < timeout_seconds:
        try:
            response = requests.get(
                status_url,
                params={"fields": "status_code,status", "access_token": ACCESS_TOKEN},
                timeout=15,
            )
            data = response.json()
            status_code = data.get("status_code", "")

            if status_code == "FINISHED":
                return True, data
            if status_code in ("ERROR", "EXPIRED"):
                return False, data
        except Exception as error:
            print(f"Error consultando container: {error}")

        time.sleep(3)

    return False, {"error": "Timeout esperando que Meta procese el container."}


def publish_to_instagram(local_image_path, product_link=None):
    if not IG_USER_ID:
        return False, "Falta IG_USER_ID"
    if not ACCESS_TOKEN:
        return False, "Falta INSTAGRAM_ACCESS_TOKEN"

    public_image_url = upload_local_image_to_web(local_image_path)
    if not public_image_url:
        return False, "No se pudo generar URL pública para la imagen."

    container_url = f"https://graph.facebook.com/{META_API_VERSION}/{IG_USER_ID}/media"
    payload = {
        "image_url": public_image_url,
        "media_type": "STORIES",
        "access_token": ACCESS_TOKEN,
    }

    try:
        response = requests.post(container_url, data=payload, timeout=30)
        response_data = response.json()
    except Exception as error:
        return False, {"error": f"Error creando container: {error}"}

    if "id" not in response_data:
        return False, response_data

    container_id = response_data["id"]
    print(f"Container creado: {container_id}")

    ready, status_data = wait_for_container(container_id)
    if not ready:
        return False, status_data

    publish_url = f"https://graph.facebook.com/{META_API_VERSION}/{IG_USER_ID}/media_publish"
    try:
        publish_response = requests.post(
            publish_url,
            data={"creation_id": container_id, "access_token": ACCESS_TOKEN},
            timeout=30,
        )
        publish_data = publish_response.json()
    except Exception as error:
        return False, {"error": f"Error publicando container: {error}"}

    if "id" in publish_data:
        return True, publish_data["id"]

    return False, publish_data


def delete_local_file(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception as error:
        print(f"No se pudo borrar {path}: {error}")


# ============================================================
# CICLO PRINCIPAL
# ============================================================

def process_catalog(auto_approve=False):
    products = fetch_all_catalog_products()

    if not products:
        if bot and TELEGRAM_CHAT_ID:
            bot.send_message(TELEGRAM_CHAT_ID, "❌ No hay productos nuevos para publicar.")
        return

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    total = len(products)

    if bot and TELEGRAM_CHAT_ID:
        bot.send_message(
            TELEGRAM_CHAT_ID,
            "🚀 <b>Procesando diseño de Story...</b>",
            parse_mode="HTML",
        )

    for index, product in enumerate(products, start=1):
        image_path = None
        try:
            image_response = requests.get(product["raw_url"], headers=headers, timeout=20)
            if image_response.status_code != 200:
                print(f"[{index}/{total}] No se pudo descargar imagen.")
                continue

            img_obj = Image.open(BytesIO(image_response.content)).convert("RGBA")

            product["ai_name"] = generate_ai_title(
                product["original_name"],
                product["permalink"],
            )

            image_path = create_story_template(product, img_obj)

            if auto_approve:
                success, result = publish_to_instagram(image_path, product["permalink"])
                if success:
                    save_to_history(product["id"])
                    print(f"[{index}/{total}] Publicado automáticamente.")

                    if bot and TELEGRAM_CHAT_ID:
                        try:
                            escaped_name = html.escape(product["original_name"])
                            escaped_ai_name = html.escape(product.get("ai_name", product["original_name"]))
                            escaped_permalink = html.escape(product["permalink"], quote=True)
                            type_str = "📦 POR ENCARGUE" if product["is_on_demand"] else f"💰 {product['price']}"

                            caption = (
                                "🎉 <b>¡Story publicada con éxito!</b>\n\n"
                                f"📦 <b>{escaped_name}</b>\n"
                                f"🤖 Título Story: <b>{escaped_ai_name}</b>\n"
                                f"Estado: <b>{type_str}</b>\n"
                                f"🎨 Color: <code>{_last_accent}</code>\n\n"
                                f'🔗 <a href="{escaped_permalink}">Ver producto en tienda</a>'
                            )

                            with open(image_path, "rb") as photo:
                                bot.send_photo(
                                    TELEGRAM_CHAT_ID,
                                    photo,
                                    caption=caption,
                                    parse_mode="HTML",
                                )
                        except Exception as err:
                            print(f"Error enviando foto a Telegram: {err}")
                else:
                    print(f"[{index}/{total}] Error Instagram: {result}")
                    if bot and TELEGRAM_CHAT_ID:
                        try:
                            safe_error = html.escape(str(result))
                            bot.send_message(
                                TELEGRAM_CHAT_ID,
                                (
                                    "❌ <b>Error en publicación de Instagram:</b>\n"
                                    f"<code>{safe_error}</code>"
                                ),
                                parse_mode="HTML",
                            )
                        except Exception as err:
                            print(f"Error enviando notificación de error a Telegram: {err}")

                delete_local_file(image_path)
                time.sleep(10)
                continue

            if not bot:
                print("TELEGRAM_BOT_TOKEN no configurado.")
                delete_local_file(image_path)
                return

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("✅ Publicar Story", callback_data=f"approve_{product['id']}"),
                InlineKeyboardButton("⏭️ Saltear", callback_data=f"skip_{product['id']}"),
            )
            markup.row(InlineKeyboardButton("🛑 Detener", callback_data="stop"))

            type_str = "📦 POR ENCARGUE" if product["is_on_demand"] else f"💰 {product['price']}"
            escaped_name = html.escape(product["original_name"])
            escaped_permalink = html.escape(product["permalink"], quote=True)
            escaped_ai_name = html.escape(product["ai_name"])

            caption = (
                f"📦 <b>[{index}/{total}] {escaped_name}</b>\n\n"
                f"🤖 Título Story: <b>{escaped_ai_name}</b>\n"
                f"Estado: <b>{type_str}</b>\n"
                f"🎨 Color: <code>{_last_accent}</code>\n\n"
                f'🔗 <a href="{escaped_permalink}">Ver producto en tienda</a>\n\n'
                "¿Deseas publicar esta Story en Instagram?"
            )

            with open(image_path, "rb") as photo:
                bot.send_photo(
                    TELEGRAM_CHAT_ID,
                    photo,
                    caption=caption,
                    reply_markup=markup,
                    parse_mode="HTML",
                )

            user_choice["action"] = None
            bot.polling(non_stop=False, timeout=30, long_polling_timeout=30)

            if user_choice["action"] == "approve":
                success, result = publish_to_instagram(image_path, product["permalink"])
                if success:
                    save_to_history(product["id"])
                    bot.send_message(
                        TELEGRAM_CHAT_ID,
                        "🎉 <b>¡Publicado con éxito en Instagram Stories!</b>",
                        parse_mode="HTML",
                    )
                else:
                    safe_error = html.escape(str(result))
                    bot.send_message(
                        TELEGRAM_CHAT_ID,
                        f"❌ <b>Error Meta:</b>\n<code>{safe_error}</code>",
                        parse_mode="HTML",
                    )
                time.sleep(3)

            elif user_choice["action"] == "skip":
                print(f"[{index}/{total}] Producto salteado.")

            elif user_choice["action"] == "stop":
                bot.send_message(
                    TELEGRAM_CHAT_ID,
                    "🏁 <b>Proceso detenido.</b>",
                    parse_mode="HTML",
                )
                delete_local_file(image_path)
                break

            delete_local_file(image_path)

        except Exception as error:
            print(f"Error procesando producto {product.get('id')}: {error}")
            delete_local_file(image_path)
            continue


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    auto_mode = os.environ.get("AUTO_APPROVE", "false").lower() == "true"
    process_catalog(auto_approve=auto_mode)
