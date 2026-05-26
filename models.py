from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nombre = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    email_verificado = db.Column(db.Boolean, default=False)
    token_verificacion = db.Column(db.String(100), nullable=True)
    analisis = db.relationship('Analisis', backref='user', lazy=True)

class Analisis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Integer, nullable=False)
    cantidad_gastos = db.Column(db.Integer, nullable=False)
    gasto_promedio = db.Column(db.Integer, nullable=False)
    categoria_max = db.Column(db.String(100), nullable=False)
    monto_max = db.Column(db.Integer, nullable=False)
    por_categoria = db.Column(db.Text, nullable=False)