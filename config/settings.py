import os
from pathlib import Path
import dj_database_url
BASE_DIR=Path(__file__).resolve().parent.parent
SECRET_KEY=os.getenv('SECRET_KEY','dev-only-change-me')
DEBUG=os.getenv('DEBUG','True').lower()=='true'
ALLOWED_HOSTS=[x.strip() for x in os.getenv('ALLOWED_HOSTS','localhost,127.0.0.1,testserver').split(',') if x.strip()]
INSTALLED_APPS=['django.contrib.contenttypes','django.contrib.auth','django.contrib.sessions','django.contrib.messages','django.contrib.staticfiles','rest_framework','corsheaders','school']
MIDDLEWARE=['django.middleware.security.SecurityMiddleware','whitenoise.middleware.WhiteNoiseMiddleware','corsheaders.middleware.CorsMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware','django.middleware.csrf.CsrfViewMiddleware','django.contrib.auth.middleware.AuthenticationMiddleware','django.contrib.messages.middleware.MessageMiddleware']
ROOT_URLCONF='config.urls'
TEMPLATES=[{'BACKEND':'django.template.backends.django.DjangoTemplates','DIRS':[],'APP_DIRS':True,'OPTIONS':{'context_processors':['django.template.context_processors.request','django.contrib.auth.context_processors.auth','django.contrib.messages.context_processors.messages']}}]
WSGI_APPLICATION='config.wsgi.application'
DATABASES={'default':dj_database_url.config(default=os.getenv('DATABASE_URL','sqlite:///'+str(BASE_DIR/'db.sqlite3')),conn_max_age=600,ssl_require=not DEBUG)}
AUTH_PASSWORD_VALIDATORS=[]
LANGUAGE_CODE='uz'
TIME_ZONE='Asia/Tashkent'
USE_I18N=True
USE_TZ=True
STATIC_URL='static/'
STATIC_ROOT=BASE_DIR/'staticfiles'
DEFAULT_AUTO_FIELD='django.db.models.BigAutoField'
CORS_ALLOWED_ORIGINS = [
    "https://29m.vercel.app",
]
CORS_ALLOW_HEADERS=['accept','authorization','content-type','user-agent','x-csrftoken','x-requested-with']
REST_FRAMEWORK={'DEFAULT_AUTHENTICATION_CLASSES':('school.authentication.SchoolJWTAuthentication',),'DEFAULT_PERMISSION_CLASSES':('rest_framework.permissions.AllowAny',),'DEFAULT_RENDERER_CLASSES':('rest_framework.renderers.JSONRenderer',)}
from datetime import timedelta
SIMPLE_JWT={'ACCESS_TOKEN_LIFETIME':timedelta(hours=12),'AUTH_HEADER_TYPES':('Bearer',)}
