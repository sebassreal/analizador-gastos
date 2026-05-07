from flask import Flask, render_template, request, jsonify
import pandas as pd
import pdfplumber
import json
import io

app = Flask(__name__)

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
            nombre = archivo.filename.lower()

            if nombre.endswith('.xlsx') or nombre.endswith('.xls'):
                df = pd.read_excel(archivo)
            elif nombre.endswith('.csv'):
                df = pd.read_csv(archivo)
            elif nombre.endswith('.pdf'):
                tablas = []
                with pdfplumber.open(archivo) as pdf:
                    for page in pdf.pages:
                        tabla = page.extract_table()
                        if tabla:
                            tablas.extend(tabla)
                if not tablas:
                    return jsonify({'error': 'No se encontraron tablas en el PDF. Probá con Excel o CSV.'})
                df = pd.DataFrame(tablas[1:], columns=tablas[0])
            else:
                return jsonify({'error': 'Formato no soportado. Usá Excel, CSV o PDF.'})

        elif request.form.get('datos_manuales'):
            datos = json.loads(request.form.get('datos_manuales'))
            df = pd.DataFrame(datos)
        else:
            return jsonify({'error': 'No se recibieron datos.'})

        resultado = analizar_gastos(df)
        return jsonify(resultado)

    except Exception as e:
        return jsonify({'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True)