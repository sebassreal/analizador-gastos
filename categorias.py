# Diccionario de categorización automática
CATEGORIAS = {
    'Supermercado': [
        'supermercado', 'carrefour', 'dia', 'coto', 'jumbo', 'walmart',
        'vea', 'disco', 'la anonima', 'changomas', 'mayorista', 'mercado'
    ],
    'Comida': [
        'restaurant', 'restaurante', 'mcdonalds', 'burger', 'pizza',
        'sushi', 'delivery', 'rappi', 'pedidosya', 'uber eats', 'cafe',
        'cafeteria', 'bar', 'parrilla', 'rotiseria', 'heladeria', 'facturas'
    ],
    'Transporte': [
        'ypf', 'shell', 'axion', 'puma', 'combustible', 'nafta', 'uber',
        'cabify', 'taxi', 'remis', 'peaje', 'estacionamiento', 'sube',
        'colectivo', 'tren', 'subte', 'auto', 'mecanico', 'gomeria'
    ],
    'Servicios': [
        'edesur', 'edenor', 'metrogas', 'aysa', 'internet', 'fibertel',
        'cablevision', 'telecom', 'personal', 'claro', 'movistar', 'telefono',
        'luz', 'gas', 'agua', 'expensas', 'alquiler'
    ],
    'Entretenimiento': [
        'netflix', 'spotify', 'disney', 'hbo', 'prime', 'youtube',
        'cine', 'teatro', 'recital', 'evento', 'juego', 'steam',
        'playstation', 'xbox', 'nintendo'
    ],
    'Salud': [
        'farmacia', 'medicina', 'medico', 'doctor', 'hospital', 'clinica',
        'dentista', 'odontologo', 'prepaga', 'osde', 'swiss medical',
        'galeno', 'laboratorio', 'analisis', 'enfermeria'
    ],
    'Ropa': [
        'zara', 'h&m', 'gap', 'adidas', 'nike', 'lacoste', 'ropa',
        'indumentaria', 'calzado', 'zapatillas', 'remera', 'pantalon',
        'vestido', 'campera', 'falabella', 'paris', 'tienda'
    ],
    'Educacion': [
        'universidad', 'colegio', 'escuela', 'instituto', 'curso',
        'udemy', 'coursera', 'libro', 'libreria', 'papeleria', 'impresion'
    ],
    'Compras Online': [
        'mercadolibre', 'amazon', 'ebay', 'aliexpress', 'shopify',
        'tiendanube', 'linio', 'falabella online'
    ],
    'Banco y Finanzas': [
        'banco', 'cajero', 'atm', 'transferencia', 'comision', 'seguro',
        'prestamo', 'cuota', 'tarjeta', 'debito', 'credito'
    ],
}

def categorizar(descripcion):
    if not descripcion:
        return 'Otros'
    desc = descripcion.lower().strip()
    for categoria, palabras in CATEGORIAS.items():
        for palabra in palabras:
            if palabra in desc:
                return categoria
    return 'Otros'