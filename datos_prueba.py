import pandas as pd

# Datos de prueba simulando un resumen de tarjeta argentina
datos = {
    'Fecha': [
        '01/03/2025', '02/03/2025', '03/03/2025', '05/03/2025',
        '07/03/2025', '08/03/2025', '10/03/2025', '12/03/2025',
        '14/03/2025', '15/03/2025', '17/03/2025', '18/03/2025',
        '20/03/2025', '22/03/2025', '25/03/2025', '27/03/2025',
        '28/03/2025', '29/03/2025', '30/03/2025', '31/03/2025',
    ],
    'Descripcion': [
        'Supermercado Dia', 'Netflix', 'YPF Combustible', 'Farmacia',
        'Restaurante', 'Ropa Zara', 'Supermercado Carrefour', 'Spotify',
        'Médico', 'Uber', 'Supermercado Dia', 'Electricidad',
        'Cine', 'Amazon', 'Supermercado Carrefour', 'Gas',
        'Restaurante', 'Farmacia', 'Uber', 'Internet',
    ],
    'Categoria': [
        'Supermercado', 'Entretenimiento', 'Transporte', 'Salud',
        'Comida', 'Ropa', 'Supermercado', 'Entretenimiento',
        'Salud', 'Transporte', 'Supermercado', 'Servicios',
        'Entretenimiento', 'Compras Online', 'Supermercado', 'Servicios',
        'Comida', 'Salud', 'Transporte', 'Servicios',
    ],
    'Monto': [
        15000, 5500, 8000, 3200,
        12000, 25000, 18000, 1200,
        8500, 2500, 14000, 9800,
        4500, 11000, 16000, 7500,
        9000, 2800, 3100, 4200,
    ]
}

df = pd.DataFrame(datos)

# Guardamos el Excel de prueba
df.to_excel('resumen_tarjeta.xlsx', index=False)
print("=== ARCHIVO DE PRUEBA CREADO ===")
print(df)
print(f"\nTotal gastado: ${df['Monto'].sum():,}")
