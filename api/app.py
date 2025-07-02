from flask import Flask, render_template, request, redirect, url_for, flash
from .models import db, User, Laporan
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
import os
from werkzeug.utils import secure_filename
import uuid
from flask import make_response
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from supabase import create_client
from functools import wraps
from flask import abort

from dotenv import load_dotenv
load_dotenv()


SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Inisialisasi aplikasi
app = Flask(__name__)

# ========================
# Konfigurasi Aplikasi
# ========================
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Konfigurasi Upload File
app.config['UPLOAD_FOLDER'] = '/static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024  # Maks 3MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


# ========================
# Fungsi Utilitas
# ========================

# Cek ekstensi file
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ========================
# Inisialisasi Library
# ========================
db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


# User Loader
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ========================
# Routes Utama
# ========================

@app.route('/')
@login_required
def home():
    return render_template('index.html', username=current_user.username)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Username atau password salah')

    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        flash('Akun berhasil dibuat, silakan login')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/laporan/export/pdf')
@login_required
def export_pdf():
    data = Laporan.query.filter_by(user_id=current_user.id).order_by(Laporan.tanggal.desc()).all()

    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    p.setFont("Helvetica-Bold", 14)
    p.drawString(50, height - 50, f"Laporan User: {current_user.username}")

    y = height - 80
    for idx, item in enumerate(data, start=1):
        if y < 100:
            p.showPage()
            y = height - 50

        p.setFont("Helvetica-Bold", 12)
        p.drawString(50, y, f"{idx}. {item.judul}")
        y -= 20
        p.setFont("Helvetica", 10)
        p.drawString(60, y, f"Tanggal: {item.tanggal.strftime('%d-%m-%Y %H:%M')}")
        y -= 15
        p.drawString(60, y, f"Isi: {item.isi}")
        y -= 40

    p.save()
    buffer.seek(0)

    return make_response(buffer.getvalue(), {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'attachment; filename=laporan.pdf'
    })

@app.route('/admin')
@admin_required
def admin_dashboard():
    users = User.query.all()
    return render_template('admin_dashboard.html', users=users)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)  # Forbidden
        return f(*args, **kwargs)
    return decorated_function
    
# ========================
# CRUD Laporan
# ========================

# List laporan
@app.route('/laporan')
@login_required
def laporan():
    data = Laporan.query.filter_by(user_id=current_user.id).order_by(Laporan.tanggal.desc()).all()
    return render_template('laporan.html', data=data)


# Tambah laporan
@app.route('/laporan/tambah', methods=['GET', 'POST'])
@login_required
def tambah_laporan():
    if file and allowed_file(file.filename):
    filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
    file_data = file.read()

    response = supabase.storage.from_('uploads').upload(f'uploads/{filename}', file_data)

    if response.get('error'):
        flash('Gagal upload file ke Supabase Storage')
        return redirect(url_for('laporan'))

    foto_url = supabase.storage.from_('uploads').get_public_url(f'uploads/{filename}')
else:
    foto_url = None

laporan = Laporan(
    judul=judul,
    isi=isi,
    foto=foto_url,
    latitude=latitude,
    longitude=longitude,
    user_id=current_user.id)

db.session.add(laporan)
db.session.commit()
flash('Laporan berhasil ditambahkan')
return redirect(url_for('laporan'))


# Edit laporan
@app.route('/laporan/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_laporan(id):
    laporan = Laporan.query.get_or_404(id)
    if request.method == 'POST':
    laporan.judul = request.form['judul']
    laporan.isi = request.form['isi']
    laporan.latitude = request.form.get('latitude')
    laporan.longitude = request.form.get('longitude')
    file = request.files.get('foto')

    if file and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
        file_data = file.read()

        response = supabase.storage.from_('uploads').upload(f'uploads/{filename}', file_data)

        if response.get('error'):
            flash('Gagal upload file ke Supabase Storage')
            return redirect(url_for('laporan'))

        foto_url = supabase.storage.from_('uploads').get_public_url(f'uploads/{filename}')
        laporan.foto = foto_url  # Update foto baru

    db.session.commit()
    flash('Laporan berhasil diupdate')
    return redirect(url_for('laporan'))


# Hapus laporan
@app.route('/laporan/hapus/<int:id>')
@login_required
def hapus_laporan(id):
    laporan = Laporan.query.get_or_404(id)
    if laporan.foto:
    try:
        path = laporan.foto.split('/storage/v1/object/public/uploads/')[-1]
        supabase.storage.from_('uploads').remove([f'uploads/{path}'])
    except Exception as e:
        print(f"Gagal menghapus file dari Supabase: {e}")

db.session.delete(laporan)
db.session.commit()
flash('Laporan berhasil dihapus')
return redirect(url_for('laporan'))

# Lihat laporan
@app.route('/admin/user/<int:user_id>/laporan')
@admin_required
def view_user_laporan(user_id):
    user = User.query.get_or_404(user_id)
    laporan_list = Laporan.query.filter_by(user_id=user.id).all()
    return render_template('view_user_laporan.html', user=user, laporan_list=laporan_list)

# ========================
# Error Handling
# ========================

@app.errorhandler(413)
def too_large(e):
    flash('File terlalu besar! Maksimum 3MB.')
    return redirect(request.url)


# ========================
# Run
# ========================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)  # Pastikan folder upload ada
    app.run(debug=True)
