import os
import random
import time
import urllib3
import requests
from requests.adapters import HTTPAdapter

# Forzar a requests a usar IPv4 (evita 'Network is unreachable' en GitHub Actions)
urllib3.util.connection.HAS_IPV6 = False

# Variables de entorno desde GitHub Secrets
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
WOO_CK = os.environ.get("WOO_CONSUMER_KEY")
WOO_CS = os.environ.get("WOO_CONSUMER_SECRET")

SITE_URL = "https://cuanticopc.com.ar"

def get_random_product_image():
    """Consulta la API de WooCommerce usando IPv4 y devuelve la URL de una imagen JPG/PNG válida."""
    endpoint = f"{SITE_URL}/wp-json/wc/v3/products"
    params = {
        "status": "publish",
        "stock_status": "instock",
        "per_page": 50
    }
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    print("Obteniendo catálogo de WooCommerce...")
    
    session = requests.Session()
    res = session.get(endpoint, params=params, auth=(WOO_CK, WOO_CS), headers=headers, timeout=20)
    
    if res.status_code != 200:
        print(f"Error al conectar con WooCommerce (Código {res.status_code}): {res.text}")
        exit(1)
        
    products = res.json()
    if not products:
        print("No se encontraron productos publicados con stock.")
        exit(1)
        
    random.shuffle(products)
    
    for product in products:
        images = product.get("images", [])
        for img in images:
            img_url = img.get("src", "")
            clean_url = img_url.split("?")[0].lower()
            if clean_url.endswith((".jpg", ".jpeg", ".png")):
                print(f"Producto seleccionado: '{product['name']}'")
                print(f"Imagen válida encontrada: {img_url}")
                return img_url

    print("No se encontró ningún producto con imágenes en formato JPG/PNG.")
    exit(1)

def post_instagram_story():
    image_url = get_random_product_image()
    
    # 1. Crear el contenedor para la Story
    container_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "media_type": "STORIES",
        "access_token": ACCESS_TOKEN
    }
    
    print("Creando contenedor de la historia en Meta...")
    res = requests.post(container_url, data=payload)
    res_data = res.json()
    
    if "id" not in res_data:
        print(f"Error al crear el contenedor: {res_data}")
        exit(1)
        
    container_id = res_data["id"]
    print(f"Contenedor creado exitosamente. ID: {container_id}")
    
    time.sleep(5)
    
    # 2. Publicar la historia
    publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
    pub_payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    
    print("Publicando historia en Instagram...")
    pub_res = requests.post(publish_url, data=pub_payload)
    pub_data = pub_res.json()
    
    if "id" in pub_data:
        print(f"¡Historia publicada con éxito! ID: {pub_data['id']}")
    else:
        print(f"Error al publicar la historia: {pub_data}")
        exit(1)

if __name__ == "__main__":
    post_instagram_story()
