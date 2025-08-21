from app import app
from models import db, Subject, User
from werkzeug.security import generate_password_hash

# قائمة المواد الأساسية
seed_subjects = [
    'اللغة العربية', 'اللغة الإنجليزية', 'التاريخ', 'الرياضيات',
    'الفيزياء', 'الكيمياء', 'الفلسفة والمنطق'
]

def create_admin_user():
    """Checks if an admin user exists, and if not, creates one."""
    if User.query.filter_by(role='admin').first() is None:
        print("Creating admin user...")
        # انتبه: استخدم كلمة مرور قوية في مشروعك الحقيقي
        hashed_password = generate_password_hash('admin') 
        
        admin_user = User(
            full_name='Admin',
            phone='01000000000',  # هذا هو اسم المستخدم للدخول
            password_hash=hashed_password,
            parent_phone='000',
            governorate='N/A',
            grade='N/A',
            status='active',      # نجعل المدير فعالاً بشكل تلقائي
            role='admin'          # أهم جزء: تحديد الدور كـ "مدير"
        )
        db.session.add(admin_user)
        db.session.commit()
        print("======================================================")
        print("Admin user created successfully!")
        print("Phone (Username): 01000000000")
        print("Password: admin")
        print("======================================================")
    else:
        print("Admin user already exists.")

def seed_db_subjects():
    """Seeds the database with initial subjects if the table is empty."""
    if Subject.query.count() == 0:
        print("Seeding subjects...")
        for name in seed_subjects:
            db.session.add(Subject(name=name))
        db.session.commit()
        print("Subjects seeded successfully.")
    else:
        print("Subjects table is not empty, skipping seeding.")

# استخدام app_context لضمان عمل كل شيء ضمن سياق التطبيق
with app.app_context():
    print("Initializing database...")
    db.create_all()
    
    # استدعاء الدوال
    seed_db_subjects()
    create_admin_user()

print("\nDatabase initialization complete!")