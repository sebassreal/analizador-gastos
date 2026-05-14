from PIL import Image, ImageDraw, ImageFont
import os

def generar_icono(nombre, size):
    img = Image.new('RGB', (size, size), color='#050a12')
    draw = ImageDraw.Draw(img)
    
    # Círculo exterior verde
    margin = size // 12
    draw.ellipse([margin, margin, size-margin, size-margin],
                 outline='#00c46a', width=size//20)
    
    # Círculo interior azul
    margin2 = size // 6
    draw.ellipse([margin2, margin2, size-margin2, size-margin2],
                 outline='#4af0ff', width=size//40)
    
    # Texto Ledgr°
    font_size = size // 5
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    
    text = 'Ledgr°'
    bbox = draw.textbbox((0,0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (size - tw) // 2
    y = (size - th) // 2
    
    draw.text((x, y), text, fill='#00c46a', font=font)
    
    img.save(f'static/{nombre}')
    print(f'Generado: static/{nombre}')

generar_icono('icon-192.png', 192)
generar_icono('icon-512.png', 512)
print('Íconos generados correctamente')