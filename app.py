from flask import Flask, render_template, request, jsonify, send_file, redirect, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
import pandas as pd
import pdfplumber
import json
import io
from categorias import categorizar
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.graphics.shapes import Drawing, Rect, Line, String
from reportlab.graphics import renderPDF
import os
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Analisis
import json
app = Flask(__name__)
app.config['SECRET_KEY'] = 'ledgr-secret-key-2025'
import os
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ledgr.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp.resend.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'resend'
app.config['MAIL_PASSWORD'] = os.environ.get('RESEND_API_KEY', 're_LEeEBT8i_AjkURXiYs6L82Gqbt6bPj1Lv')
app.config['MAIL_DEFAULT_SENDER'] = 'onboarding@resend.dev'

from flask_mail import Mail
mail = Mail(app)
csrf = CSRFProtect(app)
csrf.exempt('analizar')
csrf.exempt('comparar')
csrf.exempt('descargar_pdf')
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()
    # Migración manual de columnas nuevas
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE "user" ADD COLUMN email_verificado BOOLEAN DEFAULT FALSE'))
            conn.execute(db.text('ALTER TABLE "user" ADD COLUMN token_verificacion VARCHAR(100)'))
            conn.commit()
    except Exception:
        pass

# Rate limiting
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

# Headers de seguridad
@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

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

    # Categorización automática si no hay columna de categoría
    if not col_cat and col_desc:
        df['Categoria_Auto'] = df[col_desc].apply(categorizar)
        col_cat = 'Categoria_Auto'
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
# Alertas inteligentes
    alertas = []
    # Alertas inteligentes
    alertas = []
    
    for cat, monto in por_categoria.items():
        pct = (monto / total) * 100
        if pct > 10:
            alertas.append({
                'tipo': 'warning',
                'mensaje': f'⚠️ <strong>{cat}</strong> representa el {round(pct)}% de tus gastos totales.'
            })
    
    if len(por_categoria) > 3:
        alertas.append({
            'tipo': 'info',
            'mensaje': f'💡 Tenés gastos distribuidos en <strong>{len(por_categoria)}</strong> categorías distintas.'
        })
    
    cat_mayor = max(por_categoria, key=por_categoria.get)
    monto_mayor = por_categoria[cat_mayor]
    alertas.append({
        'tipo': 'warning',
        'mensaje': f'📊 Tu mayor gasto es <strong>{cat_mayor}</strong> con <strong>${monto_mayor:,}</strong>.'
    })
    # Categoría que supera el 40% del total
    for cat, monto in por_categoria.items():
        pct = (monto / total) * 100
        if pct > 40:
            alertas.append({
                'tipo': 'warning',
                'mensaje': f'⚠️ {cat} representa el {round(pct)}% de tus gastos totales. Considerá reducirlo.'
            })
    
    # Gasto promedio muy alto
    gasto_promedio = int(total / len(df)) if len(df) > 0 else 0
    if gasto_promedio > total * 0.15:
        alertas.append({
            'tipo': 'info',
            'mensaje': f'💡 Tu gasto promedio por transacción es alto (${gasto_promedio:,}). Revisá tus gastos grandes.'
        })
    
    # Muchas transacciones en entretenimiento
    entret = por_categoria.get('Entretenimiento', 0)
    if entret > 0 and (entret / total) * 100 > 20:
        alertas.append({
            'tipo': 'info', 
            'mensaje': f'🎬 Gastás bastante en Entretenimiento (${entret:,}). ¿Hay suscripciones que no usás?'
        })
        # Recomendaciones inteligentes
    recomendaciones = []

    # Si supermercado es muy alto
    super_monto = por_categoria.get('Supermercado', 0)
    if super_monto > 0 and (super_monto / total) * 100 > 25:
        ahorro = int(super_monto * 0.15)
        recomendaciones.append(f'🛒 Si reducís un 15% tus gastos en Supermercado podrías ahorrar <strong>${ahorro:,}</strong> por mes.')

    # Si entretenimiento es alto
    entret = por_categoria.get('Entretenimiento', 0)
    if entret > 0 and (entret / total) * 100 > 15:
        ahorro = int(entret * 0.3)
        recomendaciones.append(f'🎬 Revisá tus suscripciones de entretenimiento. Cancelar las que no usás podría ahorrarte <strong>${ahorro:,}</strong>.')

    # Si comida fuera es alto
    comida = por_categoria.get('Comida', 0)
    if comida > 0 and (comida / total) * 100 > 20:
        ahorro = int(comida * 0.4)
        recomendaciones.append(f'🍔 Comer más en casa en vez de delivery o restaurantes podría ahorrarte hasta <strong>${ahorro:,}</strong> por mes.')

    # Si transporte es alto
    transp = por_categoria.get('Transporte', 0)
    if transp > 0 and (transp / total) * 100 > 20:
        ahorro = int(transp * 0.2)
        recomendaciones.append(f'🚗 Combiná viajes en auto con transporte público para ahorrar hasta <strong>${ahorro:,}</strong>.')

    # Recomendación de ahorro general
    ahorro_general = int(total * 0.1)
    recomendaciones.append(f'💰 Si ahorrás el 10% de tus gastos totales estarías guardando <strong>${ahorro_general:,}</strong> por mes.')
    return {
        'total': int(total),
        'por_categoria': {k: int(v) for k, v in por_categoria.items()},
        'categoria_max': categoria_max,
        'monto_max': int(por_categoria[categoria_max]),
        'cantidad_gastos': len(df),
        'gasto_promedio': int(total / len(df)) if len(df) > 0 else 0,
        'alertas': alertas,
        'recomendaciones': recomendaciones
    }
    

def generar_pdf(resultado, por_categoria):
    buffer = io.BytesIO()
    from reportlab.pdfgen import canvas as pdf_canvas
    from reportlab.lib.pagesizes import A4

    w_page, h_page = A4
    c = pdf_canvas.Canvas(buffer, pagesize=A4)

    VERDE = colors.HexColor('#00c46a')
    AZUL = colors.HexColor('#4af0ff')
    FONDO = colors.HexColor('#050a12')
    FONDO2 = colors.HexColor('#070e1c')
    BLANCO = colors.HexColor('#cde8ff')
    GRIS = colors.HexColor('#2a5a7a')

    # FONDO COMPLETO
    c.setFillColor(FONDO)
    c.rect(0, 0, w_page, h_page, fill=1, stroke=0)

    # GRILLA TRON
    c.setStrokeColor(colors.HexColor('#00c46a'))
    c.setLineWidth(0.2)
    grid = 28
    for x in range(0, int(w_page)+grid, grid):
        c.setStrokeAlpha(0.06)
        c.line(x, 0, x, h_page)
    for y in range(0, int(h_page)+grid, grid):
        c.setStrokeAlpha(0.06)
        c.line(0, y, w_page, y)

    # MARCA DE AGUA
    c.saveState()
    c.setFillColor(VERDE)
    c.setFillAlpha(0.04)
    c.setFont('Helvetica-Bold', 100)
    c.translate(w_page/2, h_page/2)
    c.rotate(35)
    c.drawCentredString(0, 0, 'LEDGR')
    c.restoreState()

    # BORDE EXTERIOR VERDE
    c.setStrokeColor(VERDE)
    c.setStrokeAlpha(1)
    c.setLineWidth(2)
    c.rect(12, 12, w_page-24, h_page-24, fill=0, stroke=1)

    # BORDE INTERIOR AZUL
    c.setStrokeColor(AZUL)
    c.setLineWidth(0.4)
    c.rect(18, 18, w_page-36, h_page-36, fill=0, stroke=1)

    # ESQUINAS DECORATIVAS
    corner = 22
    c.setStrokeColor(VERDE)
    c.setLineWidth(2.5)
    for cx, cy, dx, dy in [
        (12,12,1,1),(w_page-12,12,-1,1),
        (12,h_page-12,1,-1),(w_page-12,h_page-12,-1,-1)
    ]:
        c.line(cx, cy, cx+dx*corner, cy)
        c.line(cx, cy, cx, cy+dy*corner)

    # HEADER - LOGO
    c.setFillColor(VERDE)
    c.setFillAlpha(1)
    c.setFont('Helvetica-Bold', 30)
    c.drawString(2*cm, h_page-2.4*cm, 'Ledgr')
    c.setFillColor(AZUL)
    c.drawString(2*cm+92, h_page-2.4*cm, '\u00b0')

    # TAGLINE
    c.setFillColor(GRIS)
    c.setFont('Helvetica', 7)
    c.drawString(2*cm, h_page-3*cm, 'T R A C K   W H A T   M A T T E R S')

    # LÍNEA HEADER
    c.setStrokeColor(VERDE)
    c.setLineWidth(1)
    c.line(2*cm, h_page-3.4*cm, w_page-2*cm, h_page-3.4*cm)
    c.setStrokeColor(AZUL)
    c.setLineWidth(0.3)
    c.line(2*cm, h_page-3.7*cm, w_page-2*cm, h_page-3.7*cm)

    # ÍCONOS DECORATIVOS HEADER
    c.setStrokeColor(AZUL)
    c.setStrokeAlpha(0.5)
    c.setLineWidth(0.9)
    # Casa
    ix, iy = w_page-3.5*cm, h_page-2*cm
    s = 10
    c.lines([(ix,iy-s,ix+s,iy),(ix+s,iy,ix+s,iy+s),(ix-s,iy+s,ix+s,iy+s),(ix-s,iy,ix-s,iy+s),(ix,iy-s,ix-s,iy)])
    c.rect(ix-4,iy,8,s,fill=0,stroke=1)
    # Auto
    ix2 = ix-38
    c.lines([(ix2-12,iy+4,ix2-8,iy-2),(ix2-8,iy-2,ix2+8,iy-2),(ix2+8,iy-2,ix2+12,iy+4),(ix2-12,iy+4,ix2+12,iy+4)])
    c.circle(ix2-5,iy+8,4,fill=0,stroke=1)
    c.circle(ix2+5,iy+8,4,fill=0,stroke=1)
    # Tarjeta
    ix3 = ix2-42
    c.rect(ix3-14,iy-8,28,18,fill=0,stroke=1)
    c.line(ix3-14,iy-2,ix3+14,iy-2)
    c.rect(ix3-12,iy-6,8,6,fill=0,stroke=1)

    # SECCIÓN RESUMEN
    c.setStrokeAlpha(1)
    y_pos = h_page - 4.2*cm

    c.setFillColor(AZUL)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(2*cm, y_pos, 'R E S U M E N')
    y_pos -= 0.4*cm

    # Cajas de stats
    box_w = (w_page - 4*cm) / 3
    stats = [
        ('TOTAL GASTADO', f"${resultado['total']:,}"),
        ('TRANSACCIONES', str(resultado['cantidad_gastos'])),
        ('GASTO PROMEDIO', f"${resultado['gasto_promedio']:,}"),
    ]
    for i, (label, val) in enumerate(stats):
        bx = 2*cm + i*box_w
        by = y_pos - 2*cm
        c.setFillColor(FONDO2)
        c.rect(bx, by, box_w-6, 2*cm, fill=1, stroke=0)
        c.setStrokeColor(VERDE)
        c.setLineWidth(1)
        c.rect(bx, by, box_w-6, 2*cm, fill=0, stroke=1)
        c.setFillColor(GRIS)
        c.setFont('Helvetica', 7)
        c.drawString(bx+8, by+1.6*cm, label)
        c.setFillColor(VERDE)
        c.setFont('Helvetica-Bold', 18)
        c.drawString(bx+8, by+0.5*cm, val)

    y_pos -= 2.6*cm

    # LÍNEA SEPARADORA
    c.setStrokeColor(AZUL)
    c.setLineWidth(0.4)
    c.line(2*cm, y_pos, w_page-2*cm, y_pos)
    y_pos -= 0.6*cm

    # SECCIÓN CATEGORÍAS
    c.setFillColor(AZUL)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(2*cm, y_pos, 'G A S T O S   P O R   C A T E G O R Í A')
    y_pos -= 0.5*cm

    # Header tabla
    col_widths = [8*cm, 5*cm, 3.5*cm]
    headers = ['CATEGORÍA', 'MONTO', 'PORCENTAJE']
    c.setFillColor(FONDO2)
    c.rect(2*cm, y_pos-0.6*cm, w_page-4*cm, 0.6*cm, fill=1, stroke=0)
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.8)
    c.rect(2*cm, y_pos-0.6*cm, w_page-4*cm, 0.6*cm, fill=0, stroke=1)

    x_off = 2*cm
    for i, h in enumerate(headers):
        c.setFillColor(GRIS)
        c.setFont('Helvetica-Bold', 7)
        c.drawString(x_off+6, y_pos-0.42*cm, h)
        x_off += col_widths[i]

    y_pos -= 0.6*cm
    total = resultado['total']
    row_h = 0.7*cm

    for idx, (cat, monto) in enumerate(por_categoria.items()):
        pct = round((monto / total) * 100, 1)
        bg = FONDO if idx%2==0 else FONDO2
        c.setFillColor(bg)
        c.rect(2*cm, y_pos-row_h, w_page-4*cm, row_h, fill=1, stroke=0)
        c.setStrokeColor(colors.HexColor('#00c46a20'))
        c.setLineWidth(0.3)
        c.rect(2*cm, y_pos-row_h, w_page-4*cm, row_h, fill=0, stroke=1)

        x_off = 2*cm
        c.setFillColor(BLANCO)
        c.setFont('Helvetica', 10)
        c.drawString(x_off+6, y_pos-row_h+0.2*cm, cat)
        x_off += col_widths[0]
        c.setFillColor(VERDE)
        c.setFont('Helvetica-Bold', 10)
        c.drawString(x_off+6, y_pos-row_h+0.2*cm, f'${monto:,}')
        x_off += col_widths[1]
        c.drawString(x_off+6, y_pos-row_h+0.2*cm, f'{pct}%')

        y_pos -= row_h

    # BORDE TABLA
    table_h = len(por_categoria)*row_h + 0.6*cm
    c.setStrokeColor(VERDE)
    c.setLineWidth(1)
    c.rect(2*cm, y_pos, w_page-4*cm, table_h, fill=0, stroke=1)

    y_pos -= 0.8*cm

    # ALERTA
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.4)
    c.line(2*cm, y_pos, w_page-2*cm, y_pos)
    y_pos -= 0.8*cm

    c.setFillColor(FONDO2)
    c.rect(2*cm, y_pos-1.2*cm, w_page-4*cm, 1.2*cm, fill=1, stroke=0)
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.8)
    c.rect(2*cm, y_pos-1.2*cm, w_page-4*cm, 1.2*cm, fill=0, stroke=1)
    c.setFillColor(VERDE)
    c.setFont('Helvetica', 9)
    c.drawString(2.3*cm, y_pos-0.85*cm,
        f"⚠  Mayor gasto: {resultado['categoria_max']}  —  ${resultado['monto_max']:,}")

    # ATLAS FOOTER
    fx = w_page/2
    fy = 2.8*cm
    r = 24

    # Planeta con brillo
    c.setStrokeColor(AZUL)
    c.setStrokeAlpha(0.9)
    c.setLineWidth(1.5)
    c.circle(fx, fy+r+52, r, fill=0, stroke=1)

    # Líneas latitud/longitud del planeta
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.4)
    c.setStrokeAlpha(0.5)
    for lat in [-14,-7,0,7,14]:
        import math
        half = math.sqrt(max(0,r*r-lat*lat))
        c.line(fx-half, fy+r+52+lat, fx+half, fy+r+52+lat)
    for lon in [-14,-7,0,7,14]:
        half = math.sqrt(max(0,r*r-lon*lon))
        c.line(fx+lon, fy+r+52-half, fx+lon, fy+r+52+half)

    # Continentes
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.8)
    c.setStrokeAlpha(0.7)
    c.arc(fx-18,fy+r+40,fx-4,fy+r+58,20,130)
    c.arc(fx+2,fy+r+44,fx+18,fy+r+62,10,120)
    c.arc(fx-10,fy+r+54,fx+6,fy+r+68,200,100)

    # Logo dentro del planeta
    c.setFillColor(VERDE)
    c.setFillAlpha(0.95)
    c.setFont('Helvetica-Bold', 7)
    c.drawCentredString(fx, fy+r+50, 'Ledgr\u00b0')

    # === SILUETA ATLAS MINIMALISTA ===
    ax = fx
    ay = fy + r + 52

    c.setStrokeColor(AZUL)
    c.setStrokeAlpha(0.9)

    # CABEZA
    c.setLineWidth(1.2)
    c.circle(ax, ay-r-22, 6, fill=0, stroke=1)

    # CUELLO
    c.line(ax, ay-r-16, ax, ay-r-10)

    # HOMBROS Y TORSO - forma de V invertida ancha
    c.setLineWidth(2)
    c.line(ax, ay-r-10, ax-16, ay-r-4)   # hombro izq
    c.line(ax, ay-r-10, ax+16, ay-r-4)   # hombro der

    # Torso trapezoide
    c.setLineWidth(1.5)
    c.line(ax-16, ay-r-4, ax-10, ay-r+20)  # lado izq
    c.line(ax+16, ay-r-4, ax+10, ay-r+20)  # lado der
    c.line(ax-10, ay-r+20, ax+10, ay-r+20) # cintura

    # Línea central torso
    c.setLineWidth(0.6)
    c.setStrokeColor(VERDE)
    c.line(ax, ay-r-10, ax, ay-r+20)

    # Línea pectoral
    c.arc(ax-14, ay-r-8, ax, ay-r+2, 270, 160)
    c.arc(ax, ay-r-8, ax+14, ay-r+2, 270, 160)

    # BRAZOS levantados en V hacia el planeta
    c.setStrokeColor(AZUL)
    c.setLineWidth(2.5)
    # Brazo izquierdo - arriba
    c.line(ax-16, ay-r-4, ax-22, ay-r-16)  # hombro a codo
    c.line(ax-22, ay-r-16, ax-r+4, ay-r+4) # codo a mano

    # Brazo derecho - arriba  
    c.line(ax+16, ay-r-4, ax+22, ay-r-16)
    c.line(ax+22, ay-r-16, ax+r-4, ay-r+4)

    # Manos (puños)
    c.setLineWidth(1)
    c.circle(ax-r+4, ay-r+4, 3, fill=0, stroke=1)
    c.circle(ax+r-4, ay-r+4, 3, fill=0, stroke=1)

    # CADERA
    c.setStrokeColor(AZUL)
    c.setLineWidth(1.5)
    c.line(ax-10, ay-r+20, ax-12, ay-r+28)
    c.line(ax+10, ay-r+20, ax+12, ay-r+28)
    c.line(ax-12, ay-r+28, ax+12, ay-r+28)

    # PIERNAS
    c.setLineWidth(2)
    # Izquierda
    c.line(ax-8, ay-r+28, ax-10, ay-r+46)
    c.line(ax-10, ay-r+46, ax-8, ay-r+60)
    # Derecha
    c.line(ax+8, ay-r+28, ax+10, ay-r+46)
    c.line(ax+10, ay-r+46, ax+8, ay-r+60)

    # Pies
    c.setLineWidth(1.2)
    c.line(ax-8, ay-r+60, ax-15, ay-r+64)
    c.line(ax+8, ay-r+60, ax+15, ay-r+64)

    # LÍNEA BASE - Atlas parado sobre ella
    c.setStrokeColor(VERDE)
    c.setLineWidth(1)
    c.setStrokeAlpha(0.6)
    c.line(ax-30, ay-r+65, ax+30, ay-r+65)

    # Texto footer
    c.setFillColor(GRIS)
    c.setFillAlpha(1)
    c.setFont('Helvetica', 6)
    c.drawCentredString(fx, 1.2*cm, 'Ledgr°  ·  track what matters  ·  ledgr-t1o0.onrender.com')

    # LÍNEA FOOTER
    c.setStrokeColor(VERDE)
    c.setStrokeAlpha(1)
    c.setLineWidth(0.5)
    c.line(2*cm, 1.7*cm, w_page-2*cm, 1.7*cm)

    c.save()
    buffer.seek(0)
    return buffer
@app.route('/registro', methods=['GET', 'POST'])
def registro():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        password = request.form.get('password')

        if User.query.filter_by(email=email).first():
            return jsonify({'error': 'El email ya está registrado.'})

        import secrets
        token = secrets.token_urlsafe(32)

        nuevo_usuario = User(
            nombre=nombre,
            email=email,
            password=generate_password_hash(password),
            email_verificado=False,
            token_verificacion=token
        )
        db.session.add(nuevo_usuario)
        db.session.commit()

        # Enviar email de verificación
        try:
            from flask_mail import Message
            link = f"https://ledgr-t1o0.onrender.com/verificar/{token}"
            msg = Message(
                subject='Verificá tu cuenta en Ledgr°',
                recipients=[email],
                html=f'''
                <div style="background:#050a12;padding:40px;font-family:Inter,sans-serif;color:#cde8ff;">
                    <h1 style="color:#00c46a;letter-spacing:2px;">Ledgr°</h1>
                    <p style="color:#6a9abc;font-size:14px;">track what matters</p>
                    <hr style="border-color:#00c46a30;margin:20px 0;">
                    <p>Hola <strong style="color:#fff">{nombre}</strong>, gracias por registrarte.</p>
                    <p style="margin-top:16px;">Para activar tu cuenta hacé clic en el botón:</p>
                    <a href="{link}" style="display:inline-block;margin-top:20px;background:transparent;color:#00c46a;border:1.5px solid #00c46a;padding:12px 24px;border-radius:8px;text-decoration:none;letter-spacing:2px;font-size:13px;">
                        ⚡ VERIFICAR CUENTA
                    </a>
                    <p style="margin-top:24px;font-size:12px;color:#2a5a7a;">Si no creaste esta cuenta podés ignorar este mensaje.</p>
                </div>
                '''
            )
            mail.send(msg)
        except Exception as e:
            print(f"Error enviando email: {e}")

        return jsonify({'ok': True, 'nombre': nombre, 'verificacion': True})
    from flask_wtf.csrf import generate_csrf
    return render_template('registro.html', csrf_token=generate_csrf())
@app.route('/verificar/<token>')
def verificar_email(token):
    user = User.query.filter_by(token_verificacion=token).first()
    if not user:
        return '<h1 style="color:red">Token inválido</h1>'
    user.email_verificado = True
    user.token_verificacion = None
    db.session.commit()
    login_user(user)
    return redirect('/')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password, password):
            return jsonify({'error': 'Email o contraseña incorrectos.'})
        login_user(user)
        return jsonify({'ok': True, 'nombre': user.nombre})
    from flask_wtf.csrf import generate_csrf
    return render_template('login.html', csrf_token=generate_csrf())

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'ok': True})

@app.route('/historial')
@login_required
def historial():
    analisis = Analisis.query.filter_by(user_id=current_user.id).order_by(Analisis.fecha.desc()).limit(10).all()
    resultado = []
    for a in analisis:
        resultado.append({
            'id': a.id,
            'fecha': a.fecha.strftime('%d/%m/%Y %H:%M'),
            'total': a.total,
            'cantidad_gastos': a.cantidad_gastos,
            'categoria_max': a.categoria_max,
            'monto_max': a.monto_max,
            'por_categoria': json.loads(a.por_categoria)
        })
    return jsonify(resultado)
@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    return send_file('static/sw.js', mimetype='application/javascript')
@app.route('/')
def index():
    from flask_wtf.csrf import generate_csrf
    nombre = current_user.nombre if current_user.is_authenticated else None
    csrf_token = generate_csrf()
    response = make_response(render_template('index.html', nombre=nombre, csrf_token=csrf_token))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response
def index():
    return render_template('index.html')
@limiter.limit("10 per minute")
@csrf.exempt
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

        # Guardar en historial si está logueado
        if current_user.is_authenticated:
            nuevo = Analisis(
                user_id=current_user.id,
                total=resultado['total'],
                cantidad_gastos=resultado['cantidad_gastos'],
                gasto_promedio=resultado['gasto_promedio'],
                categoria_max=resultado['categoria_max'],
                monto_max=resultado['monto_max'],
                por_categoria=json.dumps(resultado['por_categoria'])
            )
            db.session.add(nuevo)
            db.session.commit()

        return jsonify(resultado)

    except Exception as e:
        return jsonify({'error': 'Ocurrió un error al procesar el archivo. Verificá que el formato sea correcto.'})

@app.errorhandler(413)
def archivo_muy_grande(e):
    return jsonify({'error': 'El archivo es demasiado grande. Máximo 5MB.'}), 413
@limiter.limit("10 per minute")
@csrf.exempt
@app.route('/comparar', methods=['POST'])
@limiter.limit("10 per minute")
def comparar():
    try:
        def leer_archivo(key):
            archivo = request.files.get(key)
            if not archivo or archivo.filename == '':
                return None
            nombre = archivo.filename.lower()
            if not extension_permitida(nombre):
                return None
            contenido = archivo.read()
            if nombre.endswith('.xlsx') or nombre.endswith('.xls'):
                return pd.read_excel(io.BytesIO(contenido))
            elif nombre.endswith('.csv'):
                return pd.read_csv(io.BytesIO(contenido))
            elif nombre.endswith('.pdf'):
                tablas = []
                with pdfplumber.open(io.BytesIO(contenido)) as pdf:
                    for page in pdf.pages:
                        tabla = page.extract_table()
                        if tabla:
                            tablas.extend(tabla)
                if not tablas:
                    return None
                return pd.DataFrame(tablas[1:], columns=tablas[0])
            return None

        df1 = leer_archivo('archivo1')
        df2 = leer_archivo('archivo2')

        if df1 is None or df2 is None:
            return jsonify({'error': 'Necesitás subir dos archivos válidos.'})

        r1 = analizar_gastos(df1)
        r2 = analizar_gastos(df2)

        # Comparación por categoría
        cats = set(list(r1['por_categoria'].keys()) + list(r2['por_categoria'].keys()))
        comparacion = {}
        for cat in cats:
            m1 = r1['por_categoria'].get(cat, 0)
            m2 = r2['por_categoria'].get(cat, 0)
            diff = m2 - m1
            pct = round((diff / m1 * 100), 1) if m1 > 0 else 100
            comparacion[cat] = {
                'mes1': m1, 'mes2': m2,
                'diff': diff, 'pct': pct
            }

        return jsonify({
            'mes1': r1,
            'mes2': r2,
            'comparacion': comparacion
        })

    except Exception as e:
        return jsonify({'error': 'Error al comparar los archivos.'}) 
    

@csrf.exempt
@app.route('/descargar-pdf', methods=['POST'])
def descargar_pdf():
    try:
        datos = json.loads(request.form.get('resultado'))
        por_categoria = datos['por_categoria']
        buffer = generar_pdf(datos, por_categoria)
        return send_file(buffer, as_attachment=True,
            download_name='informe_ledgr.pdf',
            mimetype='application/pdf')
    except Exception as e:
        return jsonify({'error': str(e)})
@app.route('/tendencias') 
@login_required
def tendencias():
    analisis = Analisis.query.filter_by(user_id=current_user.id).order_by(Analisis.fecha.asc()).all()
    
    if len(analisis) < 2:
        return jsonify({'error': 'Necesitás al menos 2 análisis guardados para ver tendencias.'})
    
    resultado = []
    for a in analisis:
        cats = json.loads(a.por_categoria)
        resultado.append({
            'fecha': a.fecha.strftime('%d/%m/%Y'),
            'total': a.total,
            'categorias': cats
        })
    
    # Calcular tendencia general
    totales = [a['total'] for a in resultado]
    tendencia = 'al alza' if totales[-1] > totales[0] else 'a la baja'
    variacion = round(((totales[-1] - totales[0]) / totales[0]) * 100, 1)
    
    return jsonify({
        'historial': resultado,
        'tendencia': tendencia,
        'variacion': variacion
    })
if __name__ == '__main__':
    app.run(debug=True)