from flask import Flask, render_template, request, jsonify, send_file, redirect, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
import pandas as pd
import pdfplumber
import json
import io
import os
import math
from datetime import datetime, timedelta
from categorias import categorizar
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Analisis, Suscripcion
import mercadopago

app = Flask(__name__)
app.config['SECRET_KEY'] = 'ledgr-secret-key-2025'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///ledgr.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
app.config['MAIL_SERVER'] = 'smtp.resend.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'resend'
app.config['MAIL_PASSWORD'] = os.environ.get('RESEND_API_KEY', 're_LEeEBT8i_AjkURXiYs6L82Gqbt6bPj1Lv')
app.config['MAIL_DEFAULT_SENDER'] = 'onboarding@resend.dev'

MP_ACCESS_TOKEN = os.environ.get('MP_ACCESS_TOKEN', 'APP_USR-2387477710275035-060121-9ecaab65534abbcb341441a516a8280f-3442108225')
MP_PUBLIC_KEY = os.environ.get('MP_PUBLIC_KEY', 'APP_USR-d8e48d05-19ff-42cc-8e1d-6381dba4fb37')

from flask_mail import Mail
mail = Mail(app)

db.init_app(app)

csrf = CSRFProtect(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

with app.app_context():
    db.create_all()
    try:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE "user" ADD COLUMN email_verificado BOOLEAN DEFAULT FALSE'))
            conn.execute(db.text('ALTER TABLE "user" ADD COLUMN token_verificacion VARCHAR(100)'))
            conn.commit()
    except Exception:
        pass

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def es_pro():
    if not current_user.is_authenticated:
        return False
    sus = Suscripcion.query.filter_by(user_id=current_user.id).first()
    if not sus or sus.plan == 'free':
        return False
    if sus.fecha_vencimiento and sus.fecha_vencimiento < datetime.utcnow():
        sus.plan = 'free'
        db.session.commit()
        return False
    return True

@app.after_request
def security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'
    return response

EXTENSIONES_PERMITIDAS = {'xlsx', 'xls', 'csv', 'pdf'}

def extension_permitida(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in EXTENSIONES_PERMITIDAS

def analizar_gastos(df):
    df.columns = [c.strip() for c in df.columns]
    col_monto = next((c for c in df.columns if 'monto' in c.lower() or 'importe' in c.lower() or 'amount' in c.lower()), df.columns[-1])
    col_cat = next((c for c in df.columns if 'categ' in c.lower()), None)
    col_desc = next((c for c in df.columns if 'desc' in c.lower() or 'concepto' in c.lower()), None)

    if not col_cat and col_desc:
        df['Categoria_Auto'] = df[col_desc].apply(categorizar)
        col_cat = 'Categoria_Auto'

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

    # Recomendaciones inteligentes
    recomendaciones = []
    super_monto = por_categoria.get('Supermercado', 0)
    if super_monto > 0 and (super_monto / total) * 100 > 25:
        ahorro = int(super_monto * 0.15)
        recomendaciones.append(f'🛒 Si reducís un 15% tus gastos en Supermercado podrías ahorrar <strong>${ahorro:,}</strong> por mes.')
    entret = por_categoria.get('Entretenimiento', 0)
    if entret > 0 and (entret / total) * 100 > 15:
        ahorro = int(entret * 0.3)
        recomendaciones.append(f'🎬 Revisá tus suscripciones. Cancelar las que no usás podría ahorrarte <strong>${ahorro:,}</strong>.')
    comida = por_categoria.get('Comida', 0)
    if comida > 0 and (comida / total) * 100 > 20:
        ahorro = int(comida * 0.4)
        recomendaciones.append(f'🍔 Comer más en casa podría ahorrarte hasta <strong>${ahorro:,}</strong> por mes.')
    transp = por_categoria.get('Transporte', 0)
    if transp > 0 and (transp / total) * 100 > 20:
        ahorro = int(transp * 0.2)
        recomendaciones.append(f'🚗 Combiná viajes en auto con transporte público para ahorrar hasta <strong>${ahorro:,}</strong>.')
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

def generar_pdf(resultado, por_categoria, graficos={}):
    buffer = io.BytesIO()
    from reportlab.pdfgen import canvas as pdf_canvas

    w_page, h_page = A4
    c = pdf_canvas.Canvas(buffer, pagesize=A4)

    VERDE = colors.HexColor('#00c46a')
    AZUL = colors.HexColor('#4af0ff')
    FONDO = colors.HexColor('#050a12')
    FONDO2 = colors.HexColor('#070e1c')
    BLANCO = colors.HexColor('#cde8ff')
    GRIS = colors.HexColor('#2a5a7a')

    c.setFillColor(FONDO)
    c.rect(0, 0, w_page, h_page, fill=1, stroke=0)

    c.setStrokeColor(colors.HexColor('#00c46a'))
    c.setLineWidth(0.2)
    grid = 28
    for x in range(0, int(w_page)+grid, grid):
        c.setStrokeAlpha(0.06)
        c.line(x, 0, x, h_page)
    for y in range(0, int(h_page)+grid, grid):
        c.setStrokeAlpha(0.06)
        c.line(0, y, w_page, y)

    c.saveState()
    c.setFillColor(VERDE)
    c.setFillAlpha(0.04)
    c.setFont('Helvetica-Bold', 100)
    c.translate(w_page/2, h_page/2)
    c.rotate(35)
    c.drawCentredString(0, 0, 'LEDGR')
    c.restoreState()

    c.setStrokeColor(VERDE)
    c.setStrokeAlpha(1)
    c.setLineWidth(2)
    c.rect(12, 12, w_page-24, h_page-24, fill=0, stroke=1)
    c.setStrokeColor(AZUL)
    c.setLineWidth(0.4)
    c.rect(18, 18, w_page-36, h_page-36, fill=0, stroke=1)

    corner = 22
    c.setStrokeColor(VERDE)
    c.setLineWidth(2.5)
    for cx, cy, dx, dy in [(12,12,1,1),(w_page-12,12,-1,1),(12,h_page-12,1,-1),(w_page-12,h_page-12,-1,-1)]:
        c.line(cx, cy, cx+dx*corner, cy)
        c.line(cx, cy, cx, cy+dy*corner)

    c.setFillColor(VERDE)
    c.setFillAlpha(1)
    c.setFont('Helvetica-Bold', 30)
    c.drawString(2*cm, h_page-2.4*cm, 'Ledgr')
    c.setFillColor(AZUL)
    c.drawString(2*cm+92, h_page-2.4*cm, '\u00b0')
    c.setFillColor(GRIS)
    c.setFont('Helvetica', 7)
    c.drawString(2*cm, h_page-3*cm, 'T R A C K   W H A T   M A T T E R S')
    c.setStrokeColor(VERDE)
    c.setLineWidth(1)
    c.line(2*cm, h_page-3.4*cm, w_page-2*cm, h_page-3.4*cm)
    c.setStrokeColor(AZUL)
    c.setLineWidth(0.3)
    c.line(2*cm, h_page-3.7*cm, w_page-2*cm, h_page-3.7*cm)

    c.setStrokeAlpha(1)
    y_pos = h_page - 4.2*cm
    c.setFillColor(AZUL)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(2*cm, y_pos, 'R E S U M E N')
    y_pos -= 0.4*cm

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
    c.setStrokeColor(AZUL)
    c.setLineWidth(0.4)
    c.line(2*cm, y_pos, w_page-2*cm, y_pos)
    y_pos -= 0.6*cm

    c.setFillColor(AZUL)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(2*cm, y_pos, 'G A S T O S   P O R   C A T E G O R Í A')
    y_pos -= 0.5*cm

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

    table_h = len(por_categoria)*row_h + 0.6*cm
    c.setStrokeColor(VERDE)
    c.setLineWidth(1)
    c.rect(2*cm, y_pos, w_page-4*cm, table_h, fill=0, stroke=1)

    y_pos -= 0.8*cm
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
    c.drawString(2.3*cm, y_pos-0.85*cm, f"⚠  Mayor gasto: {resultado['categoria_max']}  —  ${resultado['monto_max']:,}")
# GRÁFICOS (solo plan Pro)
    if graficos:
        import base64
        from reportlab.lib.utils import ImageReader
        
        y_graficos = y_pos - 1*cm
        
        graf_titulos = {
            'donut-chart': 'DISTRIBUCIÓN POR CATEGORÍA',
            'bar-chart': 'RANKING DE GASTOS',
            'treemap-chart': 'MAPA DE GASTOS',
            'radar-chart': 'RADAR DE CATEGORÍAS',
            'line-chart': 'EVOLUCIÓN Y PREDICCIÓN'
        }
        
        for graf_id, titulo in graf_titulos.items():
            if graf_id in graficos and y_graficos > 5*cm:
                img_data = graficos[graf_id].split(',')[-1]
                img_bytes = base64.b64decode(img_data)
                img_reader = ImageReader(io.BytesIO(img_bytes))
                
                graf_h = 6*cm
                graf_w = w_page - 3*cm
                
                if y_graficos - graf_h < 3*cm:
                    c.showPage()
                    # Fondo
                    c.setFillColor(FONDO)
                    c.rect(0, 0, w_page, h_page, fill=1, stroke=0)
                    # Grilla
                    c.setStrokeColor(colors.HexColor('#00c46a'))
                    c.setLineWidth(0.2)
                    for x in range(0, int(w_page)+28, 28):
                        c.setStrokeAlpha(0.06)
                        c.line(x, 0, x, h_page)
                    for y in range(0, int(h_page)+28, 28):
                        c.setStrokeAlpha(0.06)
                        c.line(0, y, w_page, y)
                    # Bordes
                    c.setStrokeColor(VERDE)
                    c.setStrokeAlpha(1)
                    c.setLineWidth(2)
                    c.rect(12, 12, w_page-24, h_page-24, fill=0, stroke=1)
                    c.setStrokeColor(AZUL)
                    c.setLineWidth(0.4)
                    c.rect(18, 18, w_page-36, h_page-36, fill=0, stroke=1)
                    # Esquinas
                    corner = 22
                    c.setStrokeColor(VERDE)
                    c.setLineWidth(2.5)
                    for cx, cy, dx, dy in [(12,12,1,1),(w_page-12,12,-1,1),(12,h_page-12,1,-1),(w_page-12,h_page-12,-1,-1)]:
                        c.line(cx, cy, cx+dx*corner, cy)
                        c.line(cx, cy, cx, cy+dy*corner)
                    y_graficos = h_page - 2*cm
                
                c.setFillColor(AZUL)
                c.setFont('Helvetica-Bold', 7)
                c.drawString(2*cm, y_graficos, titulo)
                y_graficos -= 0.3*cm
                
                c.drawImage(img_reader, 1.5*cm, y_graficos-graf_h, 
                           width=w_page-3*cm, height=graf_h,
                           preserveAspectRatio=False)
                y_graficos -= graf_h + 0.5*cm
        
        y_pos = y_graficos

    
    # ATLAS FOOTER
    fx = w_page/2
    fy = 2.8*cm
    r = 24
    c.setStrokeColor(AZUL)
    c.setStrokeAlpha(0.9)
    c.setLineWidth(1.5)
    c.circle(fx, fy+r+52, r, fill=0, stroke=1)
    c.setStrokeColor(VERDE)
    c.setLineWidth(0.4)
    c.setStrokeAlpha(0.5)
    for lat in [-14,-7,0,7,14]:
        half = math.sqrt(max(0,r*r-lat*lat))
        c.line(fx-half, fy+r+52+lat, fx+half, fy+r+52+lat)
    for lon in [-14,-7,0,7,14]:
        half = math.sqrt(max(0,r*r-lon*lon))
        c.line(fx+lon, fy+r+52-half, fx+lon, fy+r+52+half)
    c.setFillColor(VERDE)
    c.setFillAlpha(0.95)
    c.setFont('Helvetica-Bold', 7)
    c.drawCentredString(fx, fy+r+50, 'Ledgr\u00b0')

    ax = fx
    ay = fy + r + 52
    c.setStrokeColor(AZUL)
    c.setStrokeAlpha(0.9)
    c.setLineWidth(1.2)
    c.circle(ax, ay-r-22, 6, fill=0, stroke=1)
    c.line(ax, ay-r-16, ax, ay-r-10)
    c.setLineWidth(2)
    c.line(ax, ay-r-10, ax-16, ay-r-4)
    c.line(ax, ay-r-10, ax+16, ay-r-4)
    c.setLineWidth(1.5)
    c.line(ax-16, ay-r-4, ax-10, ay-r+20)
    c.line(ax+16, ay-r-4, ax+10, ay-r+20)
    c.line(ax-10, ay-r+20, ax+10, ay-r+20)
    c.setLineWidth(2.5)
    c.line(ax-16, ay-r-4, ax-22, ay-r-16)
    c.line(ax-22, ay-r-16, ax-r+4, ay-r+4)
    c.line(ax+16, ay-r-4, ax+22, ay-r-16)
    c.line(ax+22, ay-r-16, ax+r-4, ay-r+4)
    c.setLineWidth(1)
    c.circle(ax-r+4, ay-r+4, 3, fill=0, stroke=1)
    c.circle(ax+r-4, ay-r+4, 3, fill=0, stroke=1)
    c.setLineWidth(1.5)
    c.line(ax-10, ay-r+20, ax-12, ay-r+28)
    c.line(ax+10, ay-r+20, ax+12, ay-r+28)
    c.line(ax-12, ay-r+28, ax+12, ay-r+28)
    c.setLineWidth(2)
    c.line(ax-8, ay-r+28, ax-10, ay-r+46)
    c.line(ax-10, ay-r+46, ax-8, ay-r+60)
    c.line(ax+8, ay-r+28, ax+10, ay-r+46)
    c.line(ax+10, ay-r+46, ax+8, ay-r+60)
    c.setLineWidth(1.2)
    c.line(ax-8, ay-r+60, ax-15, ay-r+64)
    c.line(ax+8, ay-r+60, ax+15, ay-r+64)
    c.setStrokeColor(VERDE)
    c.setLineWidth(1)
    c.setStrokeAlpha(0.6)
    c.line(ax-30, ay-r+65, ax+30, ay-r+65)

    c.setFillColor(GRIS)
    c.setFillAlpha(1)
    c.setFont('Helvetica', 6)
    c.drawCentredString(fx, 1.2*cm, 'Ledgr°  ·  track what matters  ·  ledgr-t1o0.onrender.com')
    c.setStrokeColor(VERDE)
    c.setStrokeAlpha(1)
    c.setLineWidth(0.5)
    c.line(2*cm, 1.7*cm, w_page-2*cm, 1.7*cm)

    c.save()
    buffer.seek(0)
    return buffer

@app.route('/')
def index():
    from flask_wtf.csrf import generate_csrf
    nombre = current_user.nombre if current_user.is_authenticated else None
    csrf_token = generate_csrf()
    response = make_response(render_template('index.html', nombre=nombre, csrf_token=csrf_token))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    return response

@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json', mimetype='application/manifest+json')

@app.route('/sw.js')
def service_worker():
    return send_file('static/sw.js', mimetype='application/javascript')

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
            nombre=nombre, email=email,
            password=generate_password_hash(password),
            email_verificado=False, token_verificacion=token
        )
        db.session.add(nuevo_usuario)
        db.session.commit()
        try:
            from flask_mail import Message
            link = f"https://ledgr-t1o0.onrender.com/verificar/{token}"
            msg = Message(
                subject='Verificá tu cuenta en Ledgr°',
                recipients=[email],
                html=f'''<div style="background:#050a12;padding:40px;font-family:Inter,sans-serif;color:#cde8ff;">
                    <h1 style="color:#00c46a;">Ledgr°</h1>
                    <p>Hola <strong>{nombre}</strong>, gracias por registrarte.</p>
                    <a href="{link}" style="display:inline-block;margin-top:20px;color:#00c46a;border:1.5px solid #00c46a;padding:12px 24px;border-radius:8px;text-decoration:none;">⚡ VERIFICAR CUENTA</a>
                </div>'''
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
    return redirect('/')

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

@csrf.exempt
@app.route('/analizar', methods=['POST'])
@limiter.limit("10 per minute")
def analizar():
    try:
        if 'archivo' in request.files and request.files['archivo'].filename != '':
            archivo = request.files['archivo']
            nombre = archivo.filename
            if not extension_permitida(nombre):
                return jsonify({'error': 'Formato no permitido. Usá Excel, CSV o PDF.'})
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
                    return jsonify({'error': 'No se encontraron tablas en el PDF.'})
                df = pd.DataFrame(tablas[1:], columns=tablas[0])
            if df.empty:
                return jsonify({'error': 'El archivo no tiene datos.'})
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
        resultado['es_pro'] = es_pro()

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
        return jsonify({'error': 'Ocurrió un error al procesar el archivo.'})

@app.errorhandler(413)
def archivo_muy_grande(e):
    return jsonify({'error': 'El archivo es demasiado grande. Máximo 5MB.'}), 413

@csrf.exempt
@app.route('/comparar', methods=['POST'])
@limiter.limit("10 per minute")
def comparar():
    if not es_pro():
        return jsonify({'error': 'Esta función es exclusiva del plan Pro.'}), 403
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
        cats = set(list(r1['por_categoria'].keys()) + list(r2['por_categoria'].keys()))
        comparacion = {}
        for cat in cats:
            m1 = r1['por_categoria'].get(cat, 0)
            m2 = r2['por_categoria'].get(cat, 0)
            diff = m2 - m1
            pct = round((diff / m1 * 100), 1) if m1 > 0 else 100
            comparacion[cat] = {'mes1': m1, 'mes2': m2, 'diff': diff, 'pct': pct}
        return jsonify({'mes1': r1, 'mes2': r2, 'comparacion': comparacion})
    except Exception as e:
        return jsonify({'error': 'Error al comparar los archivos.'})

@csrf.exempt
@app.route('/descargar-pdf', methods=['POST'])
def descargar_pdf():
    try:
        datos = json.loads(request.form.get('resultado'))
        por_categoria = datos['por_categoria']
        graficos = json.loads(request.form.get('graficos', '{}'))
        es_pro_user = es_pro()
        buffer = generar_pdf(datos, por_categoria, graficos if es_pro_user else {})
        return send_file(buffer, as_attachment=True,
            download_name='informe_ledgr.pdf',
            mimetype='application/pdf')
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/tendencias')
@login_required
def tendencias():
    if not es_pro():
        return jsonify({'error': 'Esta función es exclusiva del plan Pro.'}), 403
    analisis = Analisis.query.filter_by(user_id=current_user.id).order_by(Analisis.fecha.asc()).all()
    if len(analisis) < 2:
        return jsonify({'error': 'Necesitás al menos 2 análisis guardados para ver tendencias.'})
    resultado = []
    for a in analisis:
        cats = json.loads(a.por_categoria)
        resultado.append({'fecha': a.fecha.strftime('%d/%m/%Y'), 'total': a.total, 'categorias': cats})
    totales = [a['total'] for a in resultado]
    tendencia = 'al alza' if totales[-1] > totales[0] else 'a la baja'
    variacion = round(((totales[-1] - totales[0]) / totales[0]) * 100, 1)
    return jsonify({'historial': resultado, 'tendencia': tendencia, 'variacion': variacion})

@app.route('/planes')
def planes():
    from flask_wtf.csrf import generate_csrf
    nombre = current_user.nombre if current_user.is_authenticated else None
    csrf_token = generate_csrf()
    response = make_response(render_template('planes.html', nombre=nombre, csrf_token=csrf_token, mp_public_key=MP_PUBLIC_KEY))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return response

@app.route('/crear-pago', methods=['POST'])
@login_required
def crear_pago():
    try:
        sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
        plan = request.form.get('plan', 'pro_mensual')
        if plan == 'pro_mensual':
            precio = 4.99
            titulo = 'Ledgr° Pro - Plan Mensual'
        else:
            precio = 39.99
            titulo = 'Ledgr° Pro - Plan Anual'
        preference_data = {
            "items": [{"title": titulo, "quantity": 1, "unit_price": precio, "currency_id": "USD"}],
            "back_urls": {
                "success": "https://ledgr-t1o0.onrender.com/pago-exitoso",
                "failure": "https://ledgr-t1o0.onrender.com/pago-fallido",
                "pending": "https://ledgr-t1o0.onrender.com/pago-pendiente"
            },
            "auto_return": "approved",
            "external_reference": str(current_user.id),
        }
        preference_response = sdk.preference().create(preference_data)
        preference = preference_response["response"]
        return jsonify({'init_point': preference['init_point']})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/pago-exitoso')
def pago_exitoso():
    payment_id = request.args.get('payment_id')
    user_id = request.args.get('external_reference')
    if user_id:
        user = db.session.get(User, int(user_id))
        if user:
            sus = Suscripcion.query.filter_by(user_id=user.id).first()
            if not sus:
                sus = Suscripcion(user_id=user.id)
                db.session.add(sus)
            sus.plan = 'pro'
            sus.estado = 'activo'
            sus.fecha_inicio = datetime.utcnow()
            sus.fecha_vencimiento = datetime.utcnow() + timedelta(days=30)
            sus.mp_payment_id = payment_id
            db.session.commit()
            login_user(user)
    return redirect('/?pago=exitoso')

@app.route('/pago-fallido')
def pago_fallido():
    return redirect('/?pago=fallido')

@app.route('/pago-pendiente')
def pago_pendiente():
    return redirect('/?pago=pendiente')

@app.route('/verificar-plan')
@login_required
def verificar_plan():
    sus = Suscripcion.query.filter_by(user_id=current_user.id).first()
    if not sus or sus.plan == 'free':
        return jsonify({'plan': 'free'})
    if sus.fecha_vencimiento and sus.fecha_vencimiento < datetime.utcnow():
        sus.plan = 'free'
        db.session.commit()
        return jsonify({'plan': 'free'})
    return jsonify({'plan': 'pro'})

@app.route('/activar-pro-test')
@login_required
def activar_pro_test():
    sus = Suscripcion.query.filter_by(user_id=current_user.id).first()
    if not sus:
        sus = Suscripcion(user_id=current_user.id)
        db.session.add(sus)
    sus.plan = 'pro'
    sus.estado = 'activo'
    sus.fecha_inicio = datetime.utcnow()
    sus.fecha_vencimiento = datetime.utcnow() + timedelta(days=30)
    db.session.commit()
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)