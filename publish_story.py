import os
import time
import requests

# Cargar variables de entorno desde los Secrets
IG_USER_ID = os.environ.get("IG_USER_ID")
ACCESS_TOKEN = os.environ.get("INSTAGRAM_ACCESS_TOKEN")

# URL de la imagen directamente desde WooCommerce (debe ser JPG/PNG accesible públicamente)
# Cambiá esta URL por la imagen real de un producto de tu tienda para hacer la prueba
IMAGE_URL = "https://cuanticopc.com.ar/wp-content/uploads/2026/09/D_NQ_NP_2X_924842-MLA115590516980_092026-O.jpg" 

def post_instagram_story():
    # 1. Crear el contenedor para la Story
    container_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media"
    payload = {
        "image_url": IMAGE_URL,
        "media_type": "STORIES",
        "access_token": ACCESS_TOKEN
    }
    
    print("Creando contenedor de la historia...")
    res = requests.post(container_url, data=payload)
    res_data = res.json()
    
    if "id" not in res_data:
        print(f"Error al crear el contenedor: {res_data}")
        exit(1)
        
    container_id = res_data["id"]
    print(f"Contenedor creado con éxito ID: {container_id}")
    
    # Esperar 5 segundos para que los servidores de Meta procesen la imagen
    time.sleep(5)
    
    # 2. Publicar el contenedor en Instagram Stories
    publish_url = f"https://graph.facebook.com/v26.0/{IG_USER_ID}/media_publish"
    pub_payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN
    }
    
    print("Publicando la historia...")
    pub_res = requests.post(publish_url, data=pub_payload)
    pub_data = pub_res.json()
    
    if "id" in pub_data:
        print(f"¡Historia publicada con éxito! ID de la publicación: {pub_data['id']}")
    else:
        print(f"Error al publicar la historia: {pub_data}")
        exit(1)

if __name__ == "__main__":
    post_instagram_story()
