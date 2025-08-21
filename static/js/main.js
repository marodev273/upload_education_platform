document.addEventListener('DOMContentLoaded', function() {

    // ==========================================================
    // 1. إظهار وإخفاء كلمة المرور في فورم التسجيل
    // ==========================================================
    const togglePasswordIcons = document.querySelectorAll('.toggle-password');
    togglePasswordIcons.forEach(icon => {
        icon.addEventListener('click', function() {
            const passwordInput = this.previousElementSibling;
            if (passwordInput.type === 'password') {
                passwordInput.type = 'text';
                this.textContent = '🙈';
            } else {
                passwordInput.type = 'password';
                this.textContent = '👁️';
            }
        });
    });

    // ==========================================================
    // 2. التعامل مع أخطاء الفورم عند العودة من الخادم (الطريقة الجديدة)
    // ==========================================================
    const pageDataElement = document.getElementById('page-data');
    if (pageDataElement) {
        const errorField = pageDataElement.dataset.errorField;
        if (errorField) {
            const errorElementGroup = document.getElementById(errorField + '-group');
            if (errorElementGroup) {
                errorElementGroup.classList.add('input-error');
                errorElementGroup.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }
    }

    // ==========================================================
    // 3. التحكم في الوضع الداكن/الفاتح
    // ==========================================================
    const themeToggleBtn = document.getElementById('theme-toggle');
    if (themeToggleBtn) {
        const currentTheme = localStorage.getItem('theme');
        if (currentTheme === 'dark') {
            document.body.classList.add('dark-mode');
            themeToggleBtn.textContent = '☀️';
        }
        themeToggleBtn.addEventListener('click', function() {
            document.body.classList.toggle('dark-mode');
            let theme = 'light';
            if (document.body.classList.contains('dark-mode')) {
                theme = 'dark';
                themeToggleBtn.textContent = '☀️';
            } else {
                themeToggleBtn.textContent = '🌙';
            }
            localStorage.setItem('theme', theme);
        });
    }

    // ==========================================================
    // 4. التحكم في زر العودة للأعلى
    // ==========================================================
    const scrollToTopBtn = document.getElementById('scroll-to-top');
    if (scrollToTopBtn) {
        window.addEventListener('scroll', function() {
            if (window.scrollY > 200) {
                scrollToTopBtn.classList.add('visible');
            } else {
                scrollToTopBtn.classList.remove('visible');
            }
        });
        scrollToTopBtn.addEventListener('click', function() {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }

    // ==========================================================
    // 5. التحكم الديناميكي في فلاتر الصفحة الرئيسية
    // ==========================================================
    const gradeSelectHome = document.getElementById('grade-select');
    const branchSelectHome = document.getElementById('branch-select');

    if (gradeSelectHome && branchSelectHome) {
        const homeBranchOptions = {
            'الصف الأول الثانوي': ['عام'],
            'الصف الثاني الثانوي': ['علمي', 'أدبي'],
            'الصف الثالث الثانوي': ['علمي علوم', 'علمي رياضة', 'أدبي']
        };

        function updateHomeBranchOptions() {
            const selectedGrade = gradeSelectHome.value;
            const options = homeBranchOptions[selectedGrade] || [];
            branchSelectHome.innerHTML = '';
            options.forEach(optionText => {
                const option = document.createElement('option');
                option.value = optionText;
                option.textContent = optionText;
                branchSelectHome.appendChild(option);
            });
        }
        gradeSelectHome.addEventListener('change', updateHomeBranchOptions);
        updateHomeBranchOptions();
    }

    // ==========================================================
    // 6. التحكم الديناميكي في فورم التسجيل
    // ==========================================================
    const gradeSelectRegister = document.getElementById('grade-select-register');
    const branchGroupRegister = document.getElementById('branch-group-register');
    const branchSelectRegister = document.getElementById('branch-select-register');

    if (gradeSelectRegister && branchGroupRegister && branchSelectRegister) {
        const registerBranchOptions = {
            'الصف الثاني الثانوي': ['علمي', 'أدبي'],
            'الصف الثالث الثانوي': ['علمي علوم', 'علمي رياضة', 'أدبي']
        };
        function updateRegisterForm() {
            const selectedGrade = gradeSelectRegister.value;
            if (selectedGrade === 'الصف الثاني الثانوي' || selectedGrade === 'الصف الثالث الثانوي') {
                const options = registerBranchOptions[selectedGrade];
                branchGroupRegister.style.display = 'block';
                branchSelectRegister.required = true;
                branchSelectRegister.innerHTML = '<option value="" selected disabled>اختر الشعبة</option>';
                options.forEach(optionText => {
                    const option = document.createElement('option');
                    option.value = optionText;
                    option.textContent = optionText;
                    branchSelectRegister.appendChild(option);
                });
            } else {
                branchGroupRegister.style.display = 'none';
                branchSelectRegister.required = false;
                branchSelectRegister.innerHTML = '';
            }
        }
        gradeSelectRegister.addEventListener('change', updateRegisterForm);
        updateRegisterForm();
    }

    // ==========================================================
    // 7. نظام تتبع مشاهدات الفيديو
    // ==========================================================
    const videoPlayers = document.querySelectorAll('video[data-video-id]');
    videoPlayers.forEach(player => {
        const videoId = player.dataset.videoId;
        let trackedMilestones = new Set();

        const trackProgress = (progressPercentage) => {
            fetch('/track_video_watch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ video_id: videoId, progress: progressPercentage }),
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    console.log(`Tracked progress for video ${videoId} at ${progressPercentage}%`);
                }
            })
            .catch(error => console.error('Error tracking video:', error));
        };

        player.addEventListener('play', () => {
            if (!trackedMilestones.has(0)) {
                trackedMilestones.add(0);
                trackProgress(0);
            }
        });

        player.addEventListener('timeupdate', () => {
            if (!player.duration) return;
            const progress = Math.floor((player.currentTime / player.duration) * 100);
            const milestone = Math.floor(progress / 10) * 10;
            if (milestone > 0 && !trackedMilestones.has(milestone)) {
                trackedMilestones.add(milestone);
                trackProgress(milestone);
            }
        });

        player.addEventListener('ended', () => {
            if (!trackedMilestones.has(100)) {
                trackedMilestones.add(100);
                trackProgress(100);
            }
        });
    });

});

// ==========================================================
    // 8. نظام تتبع الوقت المنقضي في الصفحة
    // ==========================================================
    const pageStartTime = Date.now();

    // استخدم sendBeacon لإرسال البيانات بشكل موثوق عند مغادرة الصفحة
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            const durationSeconds = Math.round((Date.now() - pageStartTime) / 1000);
            
            // لا نرسل البيانات لو المدة قصيرة جدا (أقل من 5 ثواني)
            if (durationSeconds < 5) return;

            const data = {
                url: window.location.pathname,
                duration: durationSeconds
            };
            
            // نتأكد من أننا نرسل البيانات بصيغة صحيحة
            const blob = new Blob([JSON.stringify(data)], { type: 'application/json; charset=UTF-8' });
            navigator.sendBeacon('/api/track_page_view', blob);
        }
    });