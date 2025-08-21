from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

enrollments = db.Table('enrollments',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True)
)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    parent_phone = db.Column(db.String(20), nullable=False)
    governorate = db.Column(db.String(50), nullable=False)
    grade = db.Column(db.String(50), nullable=False)
    branch = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='pending_approval')
    role = db.Column(db.String(20), nullable=False, default='student')

    enrolled_courses = db.relationship('Course', secondary=enrollments, lazy='subquery',
        backref=db.backref('enrolled_users', lazy=True))
    def __repr__(self): return self.full_name

class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    photo = db.Column(db.String(300), nullable=True, default='default_teacher.png')
    subjects_taught = db.Column(db.String(500), nullable=True)
    grades_taught = db.Column(db.String(100), nullable=True)
    branch_specialization = db.Column(db.String(100), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, unique=True)
    user = db.relationship('User', backref=db.backref('teacher_profile', uselist=False))
    def __repr__(self): return self.name

class Subject(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    def __repr__(self): return self.name

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    thumbnail = db.Column(db.String(300), nullable=True, default='default.jpg')
    is_paid = db.Column(db.Boolean, default=False)
    price = db.Column(db.Float, nullable=True)
    grade = db.Column(db.String(50), nullable=False)
    subject_name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    teacher = db.relationship('Teacher', backref='courses')
    videos = db.relationship('Video', back_populates='course', lazy=True, cascade="all, delete-orphan")
    
    # --- تم التصحيح والإضافة هنا ---
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self): return self.title

# ... (باقي الكلاسات تبقى كما هي)

class Video(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    video_type = db.Column(db.String(20), nullable=False, default='local') 
    video_url = db.Column(db.String(300), nullable=True) 
    youtube_video_id = db.Column(db.String(50), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    course = db.relationship('Course', back_populates='videos')
    
    # --- [بداية] الإضافة الجديدة ---
    upload_task_id = db.Column(db.String(50), nullable=True) # لحفظ رقم مهمة الرفع
    # --- [نهاية] الإضافة الجديدة ---

    def __repr__(self): return self.title
    
class VideoWatch(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    watch_count = db.Column(db.Integer, default=0)
    max_progress = db.Column(db.Integer, default=0)
    last_watched = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('video.id'), nullable=False)
    user = db.relationship('User', backref='watches')
    video = db.relationship('Video', backref='watches')
    __table_args__ = (db.UniqueConstraint('user_id', 'video_id', name='_user_video_uc'),)
    def __repr__(self): return f'{self.user.full_name} watched {self.video.title}'

class PurchaseOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    receipt_image_url = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(50), default='pending')
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    user = db.relationship('User', backref='purchase_orders')
    course = db.relationship('Course', backref=db.backref('purchase_orders', cascade='all, delete-orphan'))

class PageViewLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(255), nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref=db.backref('page_views', cascade="all, delete-orphan"))
    def __repr__(self): return f'{self.user.full_name} stayed on {self.url} for {self.duration_seconds}s'


class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    order = db.Column(db.Integer)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    course = db.relationship('Course', backref=db.backref('lessons', lazy=True, cascade="all, delete-orphan"))
    attachments = db.relationship('Attachment', backref='lesson', lazy=True, cascade="all, delete-orphan")
    exams = db.relationship('Exam', backref='lesson', lazy=True, cascade="all, delete-orphan")

class Attachment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    file_url = db.Column(db.String(300), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'), nullable=False)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey('lesson.id'), nullable=False)
    questions = db.relationship('Question', backref='exam', lazy=True, cascade="all, delete-orphan")

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    option1 = db.Column(db.String(200), nullable=False)
    option2 = db.Column(db.String(200), nullable=False)
    option3 = db.Column(db.String(200), nullable=False)
    option4 = db.Column(db.String(200), nullable=False)
    correct_option = db.Column(db.Integer, nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)

class ExamResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    score = db.Column(db.Integer, nullable=False)
    total = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', backref='exam_results')
    exam = db.relationship('Exam', backref='results')