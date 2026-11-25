from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
import secrets,string
class User(models.Model):
    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    ROLE=[('admin','admin'),('teacher','teacher'),('student','student')]
    username=models.CharField(max_length=100,unique=True); password_hash=models.CharField(max_length=256); role=models.CharField(max_length=10,choices=ROLE); full_name=models.CharField(max_length=200); is_active=models.BooleanField(default=True)
    def set_password(self,p): self.password_hash=make_password(p)
    def check_password(self,p): return check_password(p,self.password_hash)
class SchoolClass(models.Model):
    name=models.CharField(max_length=30,unique=True); grade_level=models.PositiveSmallIntegerField(); section=models.CharField(max_length=5); is_active=models.BooleanField(default=True)
class Subject(models.Model):
    name=models.CharField(max_length=120,unique=True); description=models.TextField(blank=True); is_active=models.BooleanField(default=True)
class Student(models.Model):
    user=models.OneToOneField(User,null=True,on_delete=models.CASCADE); first_name=models.CharField(max_length=100); last_name=models.CharField(max_length=100); school_class=models.ForeignKey(SchoolClass,on_delete=models.PROTECT); student_code=models.CharField(max_length=20,unique=True)
class Teacher(models.Model):
    user=models.OneToOneField(User,on_delete=models.CASCADE); first_name=models.CharField(max_length=100); last_name=models.CharField(max_length=100); subject_names=models.JSONField(default=list,blank=True); assigned_classes=models.JSONField(default=list,blank=True); bio=models.TextField(blank=True); phone=models.CharField(max_length=40,blank=True)
class Test(models.Model):
    STATUS=[(x,x) for x in ['draft','scheduled','active','blocked','archived']]
    teacher=models.ForeignKey(Teacher,on_delete=models.CASCADE); subject=models.ForeignKey(Subject,on_delete=models.PROTECT); school_class=models.ForeignKey(SchoolClass,on_delete=models.PROTECT); title=models.CharField(max_length=200); description=models.TextField(blank=True); duration_minutes=models.PositiveSmallIntegerField(default=30); max_attempts=models.PositiveSmallIntegerField(default=1); starts_at=models.DateTimeField(null=True,blank=True); ends_at=models.DateTimeField(null=True,blank=True); status=models.CharField(max_length=15,choices=STATUS,default='draft'); created_at=models.DateTimeField(auto_now_add=True); updated_at=models.DateTimeField(auto_now=True)
class Question(models.Model):
    TYPES=[(x,x) for x in ['single_choice','multiple_choice','true_false','text']]
    test=models.ForeignKey(Test,on_delete=models.CASCADE,related_name='questions'); order_index=models.PositiveIntegerField(default=0); question_type=models.CharField(max_length=20,choices=TYPES); question_text=models.TextField(); points=models.PositiveSmallIntegerField(default=1); correct_text_answer=models.TextField(blank=True)
class AnswerOption(models.Model):
    question=models.ForeignKey(Question,on_delete=models.CASCADE,related_name='options'); option_text=models.TextField(); is_correct=models.BooleanField(default=False); order_index=models.PositiveIntegerField(default=0)
class Attempt(models.Model):
    STATUS=[(x,x) for x in ['in_progress','submitted','timed_out']]
    test=models.ForeignKey(Test,on_delete=models.CASCADE); student=models.ForeignKey(Student,on_delete=models.CASCADE); attempt_number=models.PositiveSmallIntegerField(default=1); status=models.CharField(max_length=20,choices=STATUS,default='in_progress'); started_at=models.DateTimeField(default=timezone.now); submitted_at=models.DateTimeField(null=True,blank=True); expires_at=models.DateTimeField(); duration_seconds=models.PositiveIntegerField(default=0); is_terminated=models.BooleanField(default=False); terminated_reason=models.TextField(blank=True)
class StudentAnswer(models.Model):
    attempt=models.ForeignKey(Attempt,on_delete=models.CASCADE,related_name='answers'); question=models.ForeignKey(Question,on_delete=models.CASCADE); selected_option_ids=models.JSONField(default=list); text_answer=models.TextField(blank=True); is_flagged=models.BooleanField(default=False); is_correct=models.BooleanField(default=False); earned_points=models.PositiveIntegerField(default=0); updated_at=models.DateTimeField(auto_now=True)
    class Meta: unique_together=[('attempt','question')]
class TestResult(models.Model):
    attempt=models.OneToOneField(Attempt,on_delete=models.CASCADE); test=models.ForeignKey(Test,on_delete=models.CASCADE); student=models.ForeignKey(Student,on_delete=models.CASCADE); teacher=models.ForeignKey(Teacher,on_delete=models.CASCADE); school_class=models.ForeignKey(SchoolClass,on_delete=models.PROTECT); total_questions=models.PositiveIntegerField(); correct_count=models.PositiveIntegerField(); wrong_count=models.PositiveIntegerField(); earned_points=models.PositiveIntegerField(); max_points=models.PositiveIntegerField(); percentage=models.FloatField(); grade=models.CharField(max_length=2); time_spent_seconds=models.PositiveIntegerField(); is_terminated=models.BooleanField(default=False); submitted_at=models.DateTimeField(default=timezone.now)
class Violation(models.Model):
    attempt=models.ForeignKey(Attempt,on_delete=models.CASCADE); test=models.ForeignKey(Test,on_delete=models.CASCADE); student=models.ForeignKey(Student,on_delete=models.CASCADE); teacher=models.ForeignKey(Teacher,on_delete=models.CASCADE); event_type=models.CharField(max_length=30); details=models.TextField(blank=True); occurred_at=models.DateTimeField(auto_now_add=True); reviewed_by_teacher=models.BooleanField(default=False)
class Setting(models.Model): key=models.CharField(max_length=100,unique=True); value=models.TextField()
class Activity(models.Model): actor_role=models.CharField(max_length=20); actor_name=models.CharField(max_length=200); action=models.CharField(max_length=250); target_type=models.CharField(max_length=60,blank=True); target_id=models.CharField(max_length=60,blank=True); details=models.TextField(blank=True); created_at=models.DateTimeField(auto_now_add=True)
