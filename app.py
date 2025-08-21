import os
import uuid
import os.path as op
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, session
from markupsafe import Markup
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from flask_admin import Admin, AdminIndexView, BaseView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_admin.form import FileUploadField

from wtforms import Form, StringField, SelectField, PasswordField
from wtforms.validators import DataRequired, Optional, ValidationError
from wtforms_sqlalchemy.fields import QuerySelectField

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.oauth2.credentials

import cloudinary
import cloudinary.uploader
import cloudinary.api
# from cloudinary.utils import cloudinary_url

from celery_worker import celery, upload_video_task

from models import db, User, Teacher, Course, Video, VideoWatch, PurchaseOrder, Subject, PageViewLog, Lesson, Attachment, Exam, Question, ExamResult

basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'site.db')).replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'a_new_secret_key_for_the_project'

temp_path = op.join(op.dirname(__file__), 'temp_uploads')
os.makedirs(temp_path, exist_ok=True)

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024

app.config.update(
    CELERY_BROKER_URL=os.environ.get('REDIS_URL'),
    CELERY_RESULT_BACKEND=os.environ.get('REDIS_URL')
)

cloudinary.config(
    cloud_name="dhu8sbqml",
    api_key="246772366114445",
    api_secret="okMM5R6IoCUB49g_BW2J4NpIU34",
    secure=True
)


os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'يرجى تسجيل الدخول للوصول إلى هذه الصفحة.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('ليس لديك الصلاحية للوصول إلى هذه الصفحة.', 'error')
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function
    
class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == 'admin'
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))
    
    @expose('/')
    def index(self, **kwargs):
        user_count = User.query.filter_by(role='student').count()
        teacher_count = Teacher.query.count()
        course_count = Course.query.count()
        return self.render('admin/dashboard.html', 
                           user_count=user_count, 
                           teacher_count=teacher_count, 
                           course_count=course_count)

class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == 'admin'
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))

class UserAdminForm(Form):
    full_name = StringField('الاسم الكامل', validators=[DataRequired()])
    phone = StringField('رقم الهاتف', validators=[DataRequired()])
    parent_phone = StringField('رقم هاتف ولي الأمر', validators=[DataRequired()])
    governorate = StringField('المحافظة', validators=[DataRequired()])
    grade = StringField('الصف', validators=[DataRequired()])
    branch = StringField('الشعبة (اختياري)')
    status = SelectField('الحالة', choices=[('pending_approval', 'بانتظار الموافقة'), ('active', 'مفعل')], validators=[DataRequired()])
    role = SelectField('الدور', choices=[('student', 'طالب'), ('teacher', 'مدرس'), ('admin', 'مدير')], validators=[DataRequired()])
    password = PasswordField('كلمة المرور (اتركه فارغاً عند التعديل لعدم التغيير)', validators=[Optional()])

class UserView(AdminModelView):
    form = UserAdminForm
    def _action_formatter(view, context, model, name):
        if model.status == 'pending_approval':
            approve_url = url_for('approve_user', user_id=model.id)
            reject_url = url_for('reject_user', user_id=model.id)
            return Markup(f'<a href="{approve_url}" class="btn btn-success btn-xs">قبول</a> <a href="{reject_url}" class="btn btn-danger btn-xs" style="margin-left: 5px;">رفض</a>')
        elif model.status == 'active': return Markup('<span class="label label-success">مفعل</span>')
        return "لا يوجد إجراء"
    can_create = True; can_edit = True
    column_list = ('full_name', 'phone', 'grade', 'status', 'role', 'actions')
    column_labels = {'full_name': 'الاسم', 'phone': 'الهاتف', 'grade': 'الصف', 'status': 'الحالة', 'role': 'الدور', 'actions': 'إجراءات'}
    column_formatters = {'actions': _action_formatter}
    def on_model_change(self, form, model, is_created):
        if form.password.data:
            model.password_hash = generate_password_hash(form.password.data)
        elif is_created:
            if not form.password.data: raise ValidationError('كلمة المرور مطلوبة عند إنشاء مستخدم جديد.')
            model.password_hash = generate_password_hash(form.password.data)

class TeacherView(AdminModelView):
    column_list = ['name', 'user', 'subjects_taught']
    column_labels = {'name': 'اسم المدرس', 'user': 'الحساب المرتبط', 'subjects_taught': 'المواد'}
    form_columns = ['name', 'photo', 'user', 'subjects_taught', 'grades_taught', 'branch_specialization']
    def user_query_factory(): return User.query.filter((User.role == 'teacher') | (User.role == 'admin')).all()
    form_extra_fields = {
        'user': QuerySelectField(label='ربط بحساب مستخدم', query_factory=user_query_factory, get_label='full_name', allow_blank=True, blank_text='-- لا يوجد --'),
        'photo': FileUploadField(label='صورة المدرس', base_path=temp_path)
    }
    def on_model_change(self, form, model, is_created):
        if form.photo.data:
            file_to_upload = form.photo.data
            file_to_upload.seek(0)
            upload_result = cloudinary.uploader.upload(file_to_upload, folder="teachers")
            model.photo = upload_result['secure_url']
            
class CourseView(AdminModelView):
    def teacher_query_factory(): return Teacher.query.all()
    def get_teacher_label(teacher):
        photo_url = teacher.photo or url_for('static', filename='img/default_teacher.png') 
        return Markup(f"<img src='{photo_url}' style='width: 30px; height: 30px; border-radius: 50%; margin-left: 10px;'>{teacher.name}")
    form_extra_fields = {
        'teacher': QuerySelectField(label='المدرس', query_factory=teacher_query_factory, get_label=get_teacher_label, allow_blank=False),
        'thumbnail': FileUploadField('الصورة المصغرة', base_path=temp_path, allowed_extensions=('jpg', 'jpeg', 'png')),
        'grade': SelectField('الصف الدراسي', choices=[('الصف الأول الثانوي', 'الصف الأول الثانوي'), ('الصف الثاني الثانوي', 'الصف الثاني الثانوي'), ('الصف الثالث الثانوي', 'الصف الثالث الثانوي')]),
        'subject_name': SelectField('المادة')
    }
    form_columns = ['title', 'description', 'grade', 'teacher', 'subject_name', 'thumbnail', 'is_paid', 'price']
    column_list = ('title', 'grade', 'teacher', 'subject_name', 'is_paid', 'price')
    column_labels = {'title': 'عنوان الكورس', 'grade': 'الصف', 'teacher': 'المدرس', 'subject_name': 'المادة', 'is_paid': 'مدفوع؟', 'price': 'السعر'}
    column_filters = ('grade', 'teacher', 'subject_name', 'is_paid')
    def get_subject_choices(self):
        with app.app_context():
            subjects = db.session.query(Subject.name, Subject.name).order_by(Subject.name).all()
            return subjects if subjects else [('لا توجد مواد', 'لا توجد مواد')]
    def create_form(self):
        form = super(CourseView, self).create_form()
        form.subject_name.choices = self.get_subject_choices()
        return form
    def edit_form(self, obj):
        form = super(CourseView, self).edit_form(obj)
        form.subject_name.choices = self.get_subject_choices()
        return form
    def on_model_change(self, form, model, is_created):
        if form.thumbnail.data:
            file_to_upload = form.thumbnail.data
            file_to_upload.seek(0)
            upload_result = cloudinary.uploader.upload(file_to_upload, folder="courses")
            model.thumbnail = upload_result['secure_url']

class VideoAdminView(AdminModelView):
    can_create = False; can_edit = True
    def _actions_formatter(view, context, model, name):
        stats_url = url_for('video_stats.details', video_id=model.id)
        edit_url = url_for('.edit_view', id=model.id, url=url_for('.index_view'))
        return Markup(f'<a href="{edit_url}" class="btn btn-default btn-xs">تعديل</a> <a href="{stats_url}" class="btn btn-info btn-xs">الإحصائيات</a>')
    column_list = ('title', 'course', 'video_type', 'actions')
    column_labels = {'title': 'عنوان الفيديو', 'course': 'الكورس', 'video_type': 'نوع الفيديو', 'actions': 'الإجراءات'}
    column_formatters = {'actions': _actions_formatter}
    form_columns = ['title', 'course', 'video_type', 'video_url', 'youtube_video_id']
    form_args = {'video_url': {'render_kw': {'readonly': True}}, 'youtube_video_id': {'render_kw': {'readonly': True}}}

class VideoCreatorView(BaseView):
    @expose('/')
    def index(self):
        return self.render('admin/video_chooser.html')

    @expose('/youtube')
    def youtube_upload(self):
        courses = Course.query.all()
        credentials = session.get('credentials')
        return self.render('admin/youtube_upload.html', courses=courses, credentials=credentials)
    
    @expose('/local')
    def local_upload(self):
        courses = Course.query.order_by(Course.title).all()
        return self.render('admin/local_video_upload.html', courses=courses)

    @expose('/api/upload_video', methods=['POST'])
    def api_upload_video(self):
        return jsonify(success=False, message="An error occurred")
    
    @expose('/api/upload_status/<task_id>')
    def api_upload_status(self, task_id):
        return jsonify({'state': 'PENDING', 'status': 'Pending...'})

class PurchaseOrderView(AdminModelView):
    can_create = False; can_edit = False; can_delete = False
    def _receipt_formatter(view, context, model, name):
        if not model.receipt_image_url:
            return ""
        return Markup(f'<a href="{model.receipt_image_url}" target="_blank"><img src="{model.receipt_image_url}" width="100"></a>')
    def _actions_formatter(view, context, model, name):
        if model.status == 'pending':
            approve_url = url_for('approve_purchase', order_id=model.id)
            reject_url = url_for('reject_purchase', order_id=model.id)
            return Markup(f'<a href="{approve_url}" class="btn btn-success btn-xs">قبول</a> <a href="{reject_url}" class="btn btn-danger btn-xs" style="margin-left: 5px;">رفض</a>')
        elif model.status == 'approved':
            return Markup('<span class="label label-success">مقبول</span>')
        else:
            return Markup('<span class="label label-danger">مرفوض</span>')
    column_list = ('user', 'course', 'receipt_image_url', 'status', 'timestamp', 'actions')
    column_labels = {'user': 'الطالب', 'course': 'الكورس', 'receipt_image_url': 'الإيصال', 'status': 'الحالة', 'timestamp': 'وقت الطلب', 'actions': 'إجراءات'}
    column_formatters = {'receipt_image_url': _receipt_formatter, 'actions': _actions_formatter}
    column_filters = ('status', 'user', 'course')
    column_default_sort = ('timestamp', True)

# --- تم التصحيح هنا: إضافة دالة index افتراضية ---
class VideoStatsView(BaseView):
    @expose('/')
    def index(self):
        flash('لعرض الإحصائيات، يرجى الذهاب إلى قائمة "إدارة الفيديوهات" واختيار "الإحصائيات" بجانب الفيديو المطلوب.', 'info')
        return redirect(url_for('video.index_view'))

    @expose('/details/<int:video_id>')
    def details(self, video_id):
        video = db.session.get(Video, video_id)
        if not video:
            flash('الفيديو غير موجود.', 'error')
            return redirect(url_for('video.index_view'))
        
        watch_logs = VideoWatch.query.filter_by(video_id=video_id).order_by(VideoWatch.last_watched.desc()).all()
        return self.render('admin/video_stats.html', video=video, watch_logs=watch_logs)

class VideoWatchView(AdminModelView):
    can_create = False; can_edit = False; can_delete = False
    column_list = ('user', 'video', 'watch_count', 'max_progress', 'last_watched')
    column_labels = {'user': 'الطالب', 'video': 'الفيديو', 'watch_count': 'عدد المشاهدات', 'max_progress': 'نسبة المشاهدة', 'last_watched': 'آخر مشاهدة'}
    column_formatters = {'max_progress': lambda v, c, m, n: f'{m.max_progress}%'}
    column_filters = ('user', 'video', 'last_watched')
    column_default_sort = ('last_watched', True)

class PageViewLogView(AdminModelView):
    can_create = False; can_edit = False
    column_list = ('user', 'url', 'duration_seconds', 'timestamp')
    column_labels = {'user': 'الطالب', 'url': 'رابط الصفحة', 'duration_seconds': 'مدة البقاء (ثواني)', 'timestamp': 'الوقت'}
    column_filters = ('user', 'url')

admin = Admin(app, name='لوحة التحكم', 
              index_view=MyAdminIndexView(name='الرئيسية', template='admin/index.html', url='/admin'), 
              template_mode='bootstrap4',
              base_template='admin/master.html')
class LessonView(AdminModelView):
    column_list = ('title', 'course', 'order')
    column_labels = {'title': 'عنوان الدرس', 'course': 'الكورس', 'order': 'الترتيب'}
    column_editable_list = ['order', 'title']
    form_columns = ['title', 'course', 'order']

class AttachmentView(AdminModelView):
    form_columns = ['title', 'lesson', 'file']
    column_list = ('title', 'lesson')
    column_labels = {'title': 'عنوان الملف', 'lesson': 'الدرس'}
    form_extra_fields = {
        'file': FileUploadField('الملف (PDF, JPG, PNG)', base_path=temp_path, allowed_extensions=('pdf', 'jpg', 'jpeg', 'png'))
    }
    def on_model_change(self, form, model, is_created):
        if form.file.data:
            file_to_upload = form.file.data
            file_to_upload.seek(0)
            upload_result = cloudinary.uploader.upload(file_to_upload, folder="attachments", resource_type="raw")
            model.file_url = upload_result['secure_url']

class ExamView(AdminModelView):
    column_list = ('title', 'lesson')
    column_labels = {'title': 'عنوان الامتحان', 'lesson': 'الدرس'}
    form_columns = ['title', 'lesson']

class QuestionView(AdminModelView):
    column_list = ('text', 'exam', 'correct_option')
    column_labels = {'text': 'نص السؤال', 'exam': 'الامتحان', 'correct_option': 'الإجابة الصحيحة'}
    form_columns = ['text', 'exam', 'option1', 'option2', 'option3', 'option4', 'correct_option']

admin.add_view(LessonView(Lesson, db.session, name='الدروس (الوحدات)', category='إدارة المحتوى'))
admin.add_view(AttachmentView(Attachment, db.session, name='المرفقات (PDF)', category='إدارة المحتوى'))
admin.add_view(ExamView(Exam, db.session, name='الامتحانات', category='إدارة المحتوى'))
admin.add_view(QuestionView(Question, db.session, name='الأسئلة', category='إدارة المحتوى'))


admin.add_view(UserView(User, db.session, name='المستخدمون', category='إدارة المحتوى'))
admin.add_view(TeacherView(Teacher, db.session, name='المدرسون', category='إدارة المحتوى'))
admin.add_view(CourseView(Course, db.session, name='الكورسات', category='إدارة المحتوى'))
admin.add_view(PurchaseOrderView(PurchaseOrder, db.session, name='طلبات الشراء', category='إدارة المحتوى'))
admin.add_view(VideoAdminView(Video, db.session, name='إدارة الفيديوهات', category='إدارة الفيديوهات', endpoint='video'))
admin.add_view(VideoCreatorView(name='إضافة فيديو جديد', endpoint='video_creator', category='إدارة الفيديوهات'))
admin.add_view(VideoWatchView(VideoWatch, db.session, name='تفاعل الطلاب', category='التحليلات'))
admin.add_view(PageViewLogView(PageViewLog, db.session, name='تتبع الصفحات', category='التحليلات')) 
admin.add_view(VideoStatsView(name='إحصائيات الفيديو', endpoint='video_stats', category='التحليلات'))

@app.route('/')
def home():
    teachers = Teacher.query.all()
    latest_courses = Course.query.order_by(Course.id.desc()).limit(3).all()
    return render_template('index.html', teachers=teachers, latest_courses=latest_courses)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('home'))
    if request.method == 'POST':
        user = User.query.filter_by(phone=request.form.get('phone')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            if user.status == 'active':
                login_user(user, remember=True)
                if user.role == 'admin': return redirect(url_for('admin.index'))
                return redirect(url_for('dashboard'))
            else:
                flash('حسابك في انتظار المراجعة والتفعيل.', 'info')
        else:
            flash('رقم الهاتف أو كلمة المرور غير صحيحة.', 'error')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        form_data = request.form
        full_name = form_data.get('full_name')
        password = form_data.get('password')
        confirm_password = form_data.get('confirm_password')

        # --- بداية التعديل ---
        # التحقق من أن الاسم ثلاثي
        if len(full_name.split()) < 3:
            flash('يجب إدخال الاسم ثلاثيًا على الأقل.', 'error_full_name')
            return render_template('register.html', form_data=form_data)
        # --- نهاية التعديل ---

        # التحقق من تطابق كلمتي المرور
        if password != confirm_password:
            flash('كلمتا المرور غير متطابقتين.', 'error_confirm_password')
            return render_template('register.html', form_data=form_data)

        hashed_password = generate_password_hash(password)
        new_user = User(
            full_name=full_name,
            phone=form_data.get('phone'),
            parent_phone=form_data.get('parent_phone'),
            governorate=form_data.get('governorate'),
            grade=form_data.get('grade'),
            branch=form_data.get('branch'),
            password_hash=hashed_password
        )
        db.session.add(new_user)
        db.session.commit()
        flash('تم إنشاء حسابك بنجاح! سيتم تفعيله من قبل الإدارة قريبًا.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html', form_data={})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', courses=current_user.enrolled_courses)

@app.route('/courses')
@login_required
def list_courses():
    grade_filter = request.args.get('grade')
    query = Course.query
    if grade_filter: query = query.filter_by(grade=grade_filter)
    courses = query.order_by(Course.id.desc()).all()
    return render_template('courses.html', courses=courses, selected_grade=grade_filter)

@app.route('/teacher/<int:teacher_id>/courses')
@login_required
def teacher_courses(teacher_id):
    teacher = db.session.get(Teacher, teacher_id)
    if not teacher:
        flash('المدرس المطلوب غير موجود.', 'error'); return redirect(url_for('home'))
    return render_template('teacher_courses.html', teacher=teacher, courses=teacher.courses)

@app.route('/course/<int:course_id>')
@login_required
def course_details(course_id):
    course = db.session.get(Course, course_id)
    if not course: 
        flash('الكورس المطلوب غير موجود.', 'error'); return redirect(url_for('list_courses'))
    if current_user.role in ['admin', 'teacher'] or course in current_user.enrolled_courses or not course.is_paid:
        return render_template('course_details.html', course=course)
    else:
        return redirect(url_for('purchase_course', course_id=course.id))

@app.route('/enroll/<int:course_id>', methods=['POST'])
@login_required
def enroll(course_id):
    course = db.session.get(Course, course_id)
    if course and not course.is_paid:
        if course not in current_user.enrolled_courses:
            current_user.enrolled_courses.append(course)
            db.session.commit()
            flash(f'لقد اشتركت بنجاح في كورس "{course.title}" المجاني!', 'success')
        return redirect(url_for('course_details', course_id=course.id))
    return redirect(url_for('list_courses'))

@app.route('/purchase/<int:course_id>', methods=['GET', 'POST'])
@login_required
def purchase_course(course_id):
    course = db.session.get(Course, course_id)
    if not course or not course.is_paid:
        flash('هذا الكورس غير متاح للشراء.', 'error')
        return redirect(url_for('list_courses'))
    if request.method == 'POST':
        file = request.files.get('receipt')
        if file:
            upload_result = cloudinary.uploader.upload(file, folder="receipts")
            receipt_url = upload_result['secure_url']
            new_order = PurchaseOrder(user_id=current_user.id, course_id=course.id, receipt_image_url=receipt_url)
            db.session.add(new_order)
            db.session.commit()
            flash('تم إرسال طلب الشراء بنجاح.', 'success')
            return redirect(url_for('list_courses'))
    return render_template('purchase_course.html', course=course)

@app.route('/edit_profile', methods=['GET', 'POST'])
@login_required
def edit_profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name')
        current_user.parent_phone = request.form.get('parent_phone')
        db.session.commit()
        flash('تم تحديث بياناتك بنجاح!', 'success')
        return redirect(url_for('dashboard'))
    return render_template('edit_profile.html')

@app.route('/api/track_page_view', methods=['POST'])
@login_required
def track_page_view():
    data = request.get_json()
    if data and data.get('duration'):
        new_log = PageViewLog(user_id=current_user.id, url=data.get('url'), duration_seconds=int(data.get('duration')))
        db.session.add(new_log)
        db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/admin/user/approve/<int:user_id>')
@login_required
@admin_required
def approve_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        user.status = 'active'; db.session.commit()
        flash(f'تم تفعيل حساب الطالب {user.full_name} بنجاح.', 'success')
    return redirect(url_for('user.index_view'))

@app.route('/admin/user/reject/<int:user_id>')
@login_required
@admin_required
def reject_user(user_id):
    user = db.session.get(User, user_id)
    if user:
        db.session.delete(user); db.session.commit()
        flash(f'تم رفض وحذف حساب الطالب {user.full_name}.', 'warning')
    return redirect(url_for('user.index_view'))

@app.route('/admin/order/approve/<int:order_id>')
@login_required
@admin_required
def approve_purchase(order_id):
    order = db.session.get(PurchaseOrder, order_id)
    if order and order.status == 'pending':
        order.user.enrolled_courses.append(order.course)
        order.status = 'approved'
        db.session.commit()
        flash(f'تم قبول طلب الطالب {order.user.full_name} وتسجيله في الكورس.', 'success')
    return redirect(url_for('purchaseorder.index_view'))

@app.route('/admin/order/reject/<int:order_id>')
@login_required
@admin_required
def reject_purchase(order_id):
    order = db.session.get(PurchaseOrder, order_id)
    if order and order.status == 'pending':
        order.status = 'rejected'
        db.session.commit()
        flash(f'تم رفض طلب الطالب {order.user.full_name}.', 'warning')
    return redirect(url_for('purchaseorder.index_view'))

@app.route('/exam/<int:exam_id>', methods=['GET', 'POST'])
@login_required
def take_exam(exam_id):
    exam = db.session.get(Exam, exam_id)
    if not exam:
        flash('هذا الامتحان غير موجود.', 'error')
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        score = 0
        total = len(exam.questions)
        for question in exam.questions:
            selected_option = request.form.get(f'question_{question.id}')
            if selected_option and int(selected_option) == question.correct_option:
                score += 1

        result = ExamResult(score=score, total=total, user_id=current_user.id, exam_id=exam.id)
        db.session.add(result)
        db.session.commit()

        flash(f'لقد أنهيت الامتحان بنجاح! نتيجتك هي: {score} من {total}', 'success')
        return redirect(url_for('dashboard'))

    return render_template('exam.html', exam=exam)

@app.route('/exam-results')
@login_required
def exam_results():
    results_by_course = {}
    results = db.session.query(ExamResult).filter_by(user_id=current_user.id).order_by(ExamResult.submitted_at.desc()).all()

    for result in results:
        course = result.exam.lesson.course
        if course not in results_by_course:
            results_by_course[course] = []
        results_by_course[course].append(result)

    return render_template('exam_results.html', results_by_course=results_by_course)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)