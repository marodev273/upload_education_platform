import os
import time
from celery import Celery
import cloudinary
import cloudinary.uploader

# -- إعدادات Celery --
CELERY_BROKER_URL = os.environ.get('REDIS_URL')
CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL')

celery = Celery('tasks', broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

# --- [الإصلاح النهائي هنا] ---
# ضع بياناتك الحقيقية هنا مباشرة
cloudinary.config(
    cloud_name="dhu8sbqml",
    api_key="246772366114445",
    api_secret="okMM5R6IoCUB49g_BW2J4NpIU34",
    secure=True
)
# --- [نهاية الإصلاح] ---


@celery.task(bind=True, throws=(Exception,))
def upload_video_task(self, temp_video_path):
    """مهمة Celery لرفع الفيديو وتحديث حالتها."""
    try:
        self.update_state(state='PROGRESS', meta={'progress': 10, 'status': 'بدء الرفع...'})
        time.sleep(1)
        self.update_state(state='PROGRESS', meta={'progress': 30, 'status': 'جاري الرفع إلى السحابة...'})

        upload_result = cloudinary.uploader.upload_large(
            temp_video_path, 
            resource_type="video", 
            folder="videos"
        )
        
        self.update_state(state='PROGRESS', meta={'progress': 90, 'status': 'إنهاء عملية الرفع...'})

        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

        return {'progress': 100, 'result': upload_result['secure_url']}
    except Exception as e:
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        raise e