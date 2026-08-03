import os
import requests

def get_data(url):
    response = requests.get(url, timeout=5)
    return response.json()

def process_image(image_path):
    f = open(image_path, 'rb')
    data = f.read()
    return len(data)
