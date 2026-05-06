from flask import Flask, render_template, request, jsonify
import pandas as pd
import json

app = Flask(__name__)

def analizar_gastos(df):
    # Total gastado
    total = df['Monto'].sum()
    
    # Gastos por categoría
    por_categoria = df.groupby('Categoria')['Monto'].sum().sort_values(ascending=False)
    
    # Categoría donde más se gastó
    categoria_max = por_categoria.index[0]
    monto_max = por_categoria.iloc[0]
    
    return {
        'total': int(total),
        'por_categoria': por_categoria.to_dict(),
        'categoria_max': categoria_max,
        'monto_max': int(monto_max),
        'cantidad_gastos': len(df),
        'gasto_promedio': int(total / len(df))
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analizar', methods=['POST'])
def analizar():
    try:
        # Si subió un archivo
        if 'archivo' in request.files and request.files['archivo'].filename != '':
            archivo = request.files['archivo']
            if archivo.filename.endswith('.xlsx') or archivo.filename.endswith('.xls'):
                df = pd.read_excel(archivo)
            elif archivo.filename.endswith('.csv'):
                df = pd.read_csv(archivo)
            else:
                return jsonify({'error': 'Formato no soportado. Usá Excel o CSV.'})
        
        # Si tipeo los datos manualmente
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