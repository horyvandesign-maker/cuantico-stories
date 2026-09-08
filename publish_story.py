import os
import random
import time
import requests

IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

SITE_URL = "https://cuanticopc.com.ar"

def clean_image_url(url):
    """Limpia la URL y fuerza extensión .jpg para la API de Meta."""
    base_url = url.split("?")[0]
    for ext in [".avif", ".webp", ".png", ".jpeg"]:
        if base_url.lower().endswith(ext):
            base_url = base_url[:-len(ext)] + ".jpg"
            break
    return base_url

def get_random_product_image():
    """Consulta el endpoint público de tienda para eludir el bloqueo de API privada."""
    # Usamos la API pública de la tienda que no requiere claves y está abierta a tráfico web
    endpoint = f"{SITE_URL}/wp-json/wc/store/v1/products"
    params = {
        "per_page": 50
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    
    print("Consultando productos desde la API pública de WooCommerce...")
    
    try:
        res = requests.get(endpoint, params=params, headers=headers, timeout=15)
    except Exception as e:
        print(f"Error de conexión al sitio: {e}")
        exit(1)
    
    if res.status_code != 200:
        print(f"Error HTTP {res.status_code} al consultar tienda.")
        exit(1)
        
    products = res.json()
    if not products:
        print("No se encontraron productos.")
        exit(1)
        
    random.shuffle(products)
    
    for product in products:
        images = product.get("images", [])
        if images:
            raw_url = images[0].get("src", "")
            final_url = clean_image_url(raw_url)
            print(f"Producto seleccionado: '{product.get('name')}'")
            print(f"Imagen lista para Meta: {final_url}")
            return final_url

    print("No se encontraron imágenes válidas.")
    exit(1)

def post_instagram_story():
    image_url = get_random_product_image()
    
    # 1. Crear el contenedor de la Historia
    container_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "media_type": "STORIES",
        "access_token": ACCESS_TOKEN
    }
    
    print("Enviando imagen a Meta Graph API...")
    res = requests.post(container_url, data=payload)
    res_data = res.json()
    
    if "id" not in res_data:
        print(f"Error en Meta: {res_data}")
        exit(1)
        
    container_id = res_data["id"]
    print(f"Contenedor listo. ID: {container_id}")
    
    time.sleep(5)
    
    # 2. Publicar la Historia
    publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
    pub_payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    
    print("Publicando Historia en Instagram...")
    pub_res = requests.post(publish_url, data=pub_payload)
    pub_data = pub_res.json()
    
    if "id" in pub_data:
        print(f"¡Éxito! Historia publicada. ID: {pub_data['id']}")
    else:
        print(f"Error al publicar: {pub_data}")
        exit(1)

if __name__ == "__main__":
    post_instagram_story()
