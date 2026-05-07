from flask import Flask, render_template, request, jsonify
import pandas as pd
import pdfplumber
import json
import io
import os

app = Flask(__name__)

# Límite de tamaño de archivo: 5MB
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Extensiones permitidas
EXTENSIONES_PERMITIDAS = {'xlsx', 'xls', 'csv', 'pdf'}

def extension_permitida(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in EXTENSIONES_PERMITIDAS

def analizar_gastos(df):
    df.columns = [c.strip() for c in df.columns]
    col_monto = next((c for c in df.columns if 'monto' in c.lower() or 'importe' in c.lower() or 'amount' in c.lower()), df.columns[-1])
    col_cat = next((c for c in df.columns if 'categ' in c.lower()), None)
    col_desc = next((c for c in df.columns if 'desc' in c.lower() or 'concepto' in c.lower()), None)

    df[col_monto] = pd.to_numeric(df[col_monto], errors='coerce').fillna(0)

    if col_cat:
        por_categoria = df.groupby(col_cat)[col_monto].sum().sort_values(ascending=False).to_dict()
    elif col_desc:
        por_categoria = df.groupby(col_desc)[col_monto].sum().sort_values(ascending=False).head(8).to_dict()
    else:
        por_categoria = {'Sin categoría': df[col_monto].sum()}

    total = df[col_monto].sum()
    categoria_max = max(por_categoria, key=por_categoria.get)

    return {
        'total': int(total),
        'por_categoria': {k: int(v) for k, v in por_categoria.items()},
        'categoria_max': categoria_max,
        'monto_max': int(por_categoria[categoria_max]),
        'cantidad_gastos': len(df),
        'gasto_promedio': int(total / len(df)) if len(df) > 0 else 0
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar():
    try:
        if 'archivo' in request.files and request.files['archivo'].filename != '':
            archivo = request.files['archivo']
            nombre = archivo.filename

            # Validar extensión
            if not extension_permitida(nombre):
                return jsonify({'error': 'Formato no permitido. Usá Excel, CSV o PDF.'})

            # Validar que el archivo no esté vacío
            contenido = archivo.read()
            if len(contenido) == 0:
                return jsonify({'error': 'El archivo está vacío.'})
            archivo.seek(0)

            nombre_lower = nombre.lower()
            if nombre_lower.endswith('.xlsx') or nombre_lower.endswith('.xls'):
                df = pd.read_excel(io.BytesIO(contenido))
            elif nombre_lower.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(contenido))
            elif nombre_lower.endswith('.pdf'):
                tablas = []
                with pdfplumber.open(io.BytesIO(contenido)) as pdf:
                    for page in pdf.pages:
                        tabla = page.extract_table()
                        if tabla:
                            tablas.extend(tabla)
                if not tablas:
                    return jsonify({'error': 'No se encontraron tablas en el PDF. Probá con Excel o CSV.'})
                df = pd.DataFrame(tablas[1:], columns=tablas[0])

            # Validar que tenga datos
            if df.empty:
                return jsonify({'error': 'El archivo no tiene datos.'})

            # Limitar filas para evitar abuso
            if len(df) > 5000:
                return jsonify({'error': 'El archivo tiene demasiadas filas. Máximo 5000.'})

        elif request.form.get('datos_manuales'):
            datos = json.loads(request.form.get('datos_manuales'))
            df = pd.DataFrame(datos)
            if df.empty:
                return jsonify({'error': 'No ingresaste ningún dato.'})
        else:
            return jsonify({'error': 'No se recibieron datos.'})

        resultado = analizar_gastos(df)
        return jsonify(resultado)

    except Exception as e:
        return jsonify({'error': 'Ocurrió un error al procesar el archivo. Verificá que el formato sea correcto.'})

@app.errorhandler(413)
def archivo_muy_grande(e):
    return jsonify({'error': 'El archivo es demasiado grande. Máximo 5MB.'}), 413

if __name__ == '__main__':
    app.run(debug=True)