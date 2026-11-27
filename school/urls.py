from django.urls import path
from . import views


urlpatterns = [
    path('health/', views.health),
    path('public/bootstrap', views.public_bootstrap),

    path('auth/admin/status', views.admin_status),
    path('auth/admin/claim', views.admin_claim),
    path('auth/admin/login', views.admin_login),
    path('auth/teacher/login', views.teacher_login),
    path('auth/student/login', views.student_login),
    path('auth/me', views.auth_me),

    path('student/tests', views.student_tests),
    path('student/tests/<int:test_id>/start', views.start_test),
    path('student/attempts/<int:attempt_id>/answer', views.save_answer),
    path('student/attempts/<int:attempt_id>/submit', views.submit_attempt),
    path('student/attempts/<int:attempt_id>/violation', views.violation),

    path('teacher/meta', views.teacher_meta),
    path('teacher/import-word', views.teacher_import_word),
    path('teacher/dashboard', views.teacher_dashboard),
    path('teacher/tests', views.teacher_tests_root),
    path('teacher/tests/<int:pk>', views.teacher_test_item),
    path('teacher/tests/<int:pk>/status', views.teacher_test_item),
    path('teacher/results', views.teacher_results),
    path('teacher/results/<int:pk>', views.teacher_result_update),
    path('teacher/statistics', views.teacher_stats),
    path('teacher/violations', views.teacher_violations),
    path('teacher/violations/<int:pk>/review', views.review_violation),
    path('teacher/profile', views.teacher_profile),

    path('admin/dashboard', views.admin_dashboard),
    path('admin/teachers', views.admin_teachers),
    path('admin/teachers/<int:pk>', views.admin_teacher_item),
    path('admin/tests', views.admin_tests),
    path('admin/tests/<int:pk>/status', views.admin_test_item),
    path('admin/tests/<int:pk>', views.admin_test_item),
    path('admin/results', views.admin_results),
    path('admin/classes', views.admin_classes),
    path('admin/classes/<int:pk>', views.admin_class_item),
    path('admin/subjects', views.admin_subjects),
    path('admin/subjects/<int:pk>', views.admin_subject_item),
    path('admin/students', views.admin_students),
    path('admin/students/<int:pk>', views.admin_student_item),
    path('admin/activity', views.admin_activity),
    path('admin/settings', views.admin_settings),
    path('auth/teacher/register', views.teacher_register),
   
]
