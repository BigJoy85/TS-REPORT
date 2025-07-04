from flask import Flask, render_template, request, redirect, url_for, flash, abort, make_response
from .models import db, User, Laporan
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from io import BytesIO
from supabase import create_client, Client
from functools import wraps
import uuid, os
from dotenv import load_dotenv

# ============================
# Load environment
# ============================
load_dotenv()

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ============================
# Flask config
# ============================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = '/tmp/uploads'
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ============================
# Utils
# ============================
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

# ============================
# Routes
# ============================
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
            if user.role == 'admin':
                return redirect(url_for('admin_laporan'))
            else:
                return redirect(url_for('home'))
        else:
            flash('Username atau password salah')

    return render_template('login.html')
    
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        user = User(username=username, password=password, role='user')
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

# ============================
# Admin Routes
# ============================
@app.route("/admin/users")
@admin_required
def admin_users():
    users = User.query.all()
    return render_template("admin_users.html", users=users)

@app.route("/admin/laporan")
@admin_required
def admin_laporan():
    laporan = Laporan.query.order_by(Laporan.tanggal.desc()).all()
    return render_template("admin_laporan.html", laporan=laporan)

@app.route('/admin/user/<int:user_id>/laporan')
@admin_required
def view_user_laporan(user_id):
    user = User.query.get_or_404(user_id)
    laporan_list = Laporan.query.filter_by(user_id=user.id).all()
    return render_template('view_user_laporan.html', user=user, laporan_list=laporan_list)

@app.route('/admin/user/<int:user_id>/hapus', methods=['POST'])
@admin_required
def hapus_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == 'admin':
        flash("Tidak bisa menghapus akun admin lain!", "danger")
        return redirect(url_for('admin_users'))

    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.username} berhasil dihapus.", "success")
    return redirect(url_for('admin_users'))

@app.route('/laporan')
@login_required
def laporan():
    data = Laporan.query.filter_by(user_id=current_user.id).order_by(Laporan.tanggal.desc()).all()
    return render_template('laporan.html', data=data)

@app.route('/laporan/tambah', methods=['GET', 'POST'])
@login_required
def tambah_laporan():
    if request.method == 'POST':
        judul = request.form['judul']
        isi = request.form['isi']
        checklist = request.form.get('checklist')
        catatan = request.form.get('catatan')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        file = request.files.get('foto')

        if checklist not in ['ok', 'tidak']:
            flash('Checklist harus Ok atau Tidak')
            return redirect(url_for('tambah_laporan'))

        foto_url = None
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
            file_data = file.read()
            response = supabase.storage.from_('uploads').upload(f'uploads/{filename}', file_data)
            if response.get('error'):
                flash('Gagal upload file ke Supabase Storage')
                return redirect(url_for('laporan'))
            foto_url = supabase.storage.from_('uploads').get_public_url(f'uploads/{filename}')

        laporan = Laporan(
            judul=judul,
            isi=isi,
            checklist=checklist,
            catatan=catatan,
            foto=foto_url,
            latitude=latitude,
            longitude=longitude,
            user_id=current_user.id
        )
        db.session.add(laporan)
        db.session.commit()
        flash('Laporan berhasil ditambahkan')
        return redirect(url_for('laporan'))

    return render_template('tambah_laporan.html')

@app.route('/laporan/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_laporan(id):
    laporan = Laporan.query.get_or_404(id)
    if laporan.user_id != 'admin':
        flash('Hanya admin yang dapat mengedit laporan')
        return redirect(url_for('laporan'))

    if request.method == 'POST':
        laporan.judul = request.form['judul']
        laporan.isi = request.form['isi']
        laporan.checklist = request.form.get('checklist')
        laporan.catatan = request.form.get('catatan')
        laporan.latitude = request.form.get('latitude')
        laporan.longitude = request.form.get('longitude')
        file = request.files.get('foto')

        if laporan.checklist not in ['ok', 'tidak']:
            flash('Checklist harus Ok atau Tidak')
            return redirect(url_for('edit_laporan', id=id))

        if file and allowed_file(file.filename):
            filename = secure_filename(f"{uuid.uuid4().hex}_{file.filename}")
            file_data = file.read()
            response = supabase.storage.from_('uploads').upload(f'uploads/{filename}', file_data)
            if response.get('error'):
                flash('Gagal upload file ke Supabase Storage')
                return redirect(url_for('laporan'))
            foto_url = supabase.storage.from_('uploads').get_public_url(f'uploads/{filename}')
            laporan.foto = foto_url

        db.session.commit()
        flash('Laporan berhasil diupdate')
        return redirect(url_for('laporan'))

    return render_template('edit_laporan.html', laporan=laporan)

@app.route('/laporan/hapus/<int:id>')
@login_required
def hapus_laporan(id):
    laporan = Laporan.query.get_or_404(id)
    if laporan.user_id != 'admin':
        flash('Hanya admin yang dapat menghapus laporan')
        return redirect(url_for('laporan'))

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
        y -= 15
        p.drawString(60, y, f"Checklist: {item.checklist}")
        y -= 15
        if item.catatan:
            p.drawString(60, y, f"Catatan: {item.catatan}")
            y -= 15
        y -= 20

    p.save()
    buffer.seek(0)

    return make_response(buffer.getvalue(), {
        'Content-Type': 'application/pdf',
        'Content-Disposition': 'attachment; filename=laporan.pdf'
    })

@app.errorhandler(413)
def too_large(e):
    flash('File terlalu besar! Maksimum 3MB.')
    return redirect(request.url)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
