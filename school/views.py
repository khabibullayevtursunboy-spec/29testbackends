import os, secrets, string, json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.db.models import Count, Avg, Q, Min, Max
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.hashers import make_password, check_password
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import AccessToken
from .models import *


# ---------------------------------------------------------------- helpers
def err(msg, code=400):
    return Response({'error': msg}, status=code)


def user_payload(u):
    if u.role == 'student':
        s = Student.objects.select_related('school_class').get(user=u)
        return {'role': 'student', 'studentId': s.id, 'firstName': s.first_name, 'lastName': s.last_name,
                'fullName': u.full_name, 'classId': s.school_class_id, 'className': s.school_class.name,
                'studentCode': s.student_code}
    if u.role == 'teacher':
        t = Teacher.objects.get(user=u)
        return {'role': 'teacher', 'userId': u.id, 'teacherId': t.id, 'username': u.username,
                'fullName': u.full_name, 'firstName': t.first_name, 'lastName': t.last_name,
                'subjectNames': t.subject_names, 'assignedClasses': t.assigned_classes,
                'bio': t.bio, 'phone': t.phone}
    return {'role': 'admin', 'fullName': u.full_name}


def token_for(u):
    tok = AccessToken()
    tok['uid'] = u.id
    tok['role'] = u.role
    return str(tok)


def actor(request, role=None):
    uid = request.user if request.user.is_authenticated else None
    if not uid:
        return None
    try:
        u = User.objects.get(id=uid.id)
    except User.DoesNotExist:
        return None
    if role and u.role != role:
        return None
    return u


def current_user(request):
    try:
        return User.objects.get(id=request.user.id)
    except Exception:
        return None


def log(role, name, action, details=''):
    Activity.objects.create(actor_role=role, actor_name=name, action=action, details=details)


def bootstrap_data():
    if not SchoolClass.objects.exists():
        for g in range(5, 12):
            for sec in ['A', 'B', 'D']:
                SchoolClass.objects.get_or_create(name=f'{g}-{sec}', defaults={'grade_level': g, 'section': sec})
    if not Subject.objects.exists():
        for n, d in [('Matematika', 'Algebra va geometriya'), ('Fizika', 'Fizika'), ('Kimyo', 'Kimyo'),
                     ('Biologiya', 'Biologiya'), ('Informatika', 'Axborot texnologiyalari'),
                     ('Ona tili va adabiyot', ''), ('Ingliz tili', ''), ('Tarix', ''), ('Geografiya', '')]:
            Subject.objects.get_or_create(name=n, defaults={'description': d})
    Setting.objects.get_or_create(key='school_name', defaults={'value': 'SCHOOL TEST SYSTEM Maktabi'})
    admin_name = os.getenv('ADMIN_USERNAME', 'admin')
    admin_pass = os.getenv('ADMIN_PASSWORD', '')
    if admin_pass and not User.objects.filter(role='admin').exists():
        u = User(username=admin_name, role='admin', full_name='Administrator',
                 password_hash=make_password(admin_pass))
        u.save()


def grade_attempt(a, terminated=False, reason=''):
    if a.status != 'in_progress':
        return
    qs = list(a.test.questions.prefetch_related('options').all())
    correct = 0
    earned = 0
    maximum = 0
    for q in qs:
        maximum += q.points
        try:
            ans = a.answers.get(question=q)
        except StudentAnswer.DoesNotExist:
            ans = StudentAnswer.objects.create(attempt=a, question=q)
        ok = False
        if q.question_type in ['single_choice', 'multiple_choice']:
            expected = sorted(q.options.filter(is_correct=True).values_list('id', flat=True))
            actual = sorted(set(ans.selected_option_ids or []))
            ok = bool(expected) and expected == actual
        else:
            expected = [x.strip().lower() for x in q.correct_text_answer.split('|') if x.strip()]
            actual = ans.text_answer.strip().lower()
            ok = bool(actual and actual in expected)
        ans.is_correct = ok
        ans.earned_points = q.points if ok else 0
        ans.save()
        correct += int(ok)
        earned += ans.earned_points
    pct = round(earned * 1000 / maximum) / 10 if maximum else 0
    grade = '5' if pct >= 86 else '4' if pct >= 71 else '3' if pct >= 56 else '2'
    now = timezone.now()
    a.status = 'timed_out' if a.expires_at <= now else 'submitted'
    a.submitted_at = now
    a.duration_seconds = max(1, int((now - a.started_at).total_seconds()))
    a.is_terminated = terminated
    a.terminated_reason = reason
    a.save()
    TestResult.objects.update_or_create(attempt=a, defaults={
        'test': a.test, 'student': a.student, 'teacher': a.test.teacher,
        'school_class': a.student.school_class, 'total_questions': len(qs), 'correct_count': correct,
        'wrong_count': len(qs) - correct, 'earned_points': earned, 'max_points': maximum,
        'percentage': pct, 'grade': grade, 'time_spent_seconds': a.duration_seconds,
        'is_terminated': terminated, 'submitted_at': now})


def test_card(t, student):
    attempts = list(Attempt.objects.filter(test=t, student=student).order_by('-id'))
    active = next((a for a in attempts if a.status == 'in_progress' and a.expires_at > timezone.now()), None)
    done = sum(1 for a in attempts if a.status != 'in_progress' or a.expires_at <= timezone.now())
    if t.status in ['blocked', 'draft', 'archived']:
        av = 'unavailable'
    elif t.starts_at and t.starts_at > timezone.now():
        av = 'upcoming'
    elif t.ends_at and t.ends_at < timezone.now():
        av = 'expired'
    else:
        av = 'active'
    return {'id': t.id, 'title': t.title, 'description': t.description, 'subjectName': t.subject.name,
            'teacherName': t.teacher.first_name + ' ' + t.teacher.last_name,
            'questionCount': t.questions.count(), 'durationMinutes': t.duration_minutes,
            'maxAttempts': t.max_attempts, 'completedAttempts': done,
            'inProgressAttemptId': active.id if active else None, 'startsAt': t.starts_at,
            'endsAt': t.ends_at, 'availability': av,
            'canStart': av == 'active' and (active is not None or done < t.max_attempts)}


# ---------------------------------------------------------------- health / public
@require_http_methods(["GET", "HEAD"])
def health(request):
    return JsonResponse({"status": "ok"})


@api_view(['GET'])
def public_bootstrap(r):
    bootstrap_data()
    return Response({
        'classes': list(SchoolClass.objects.filter(is_active=True).values('id', 'name', 'grade_level', 'section')),
        'subjects': list(Subject.objects.filter(is_active=True).values('id', 'name', 'description')),
        'schoolName': Setting.objects.get(key='school_name').value})


# ---------------------------------------------------------------- auth
@api_view(['GET'])
def admin_status(r):
    return Response({'configured': User.objects.filter(role='admin').exists(),
                     'envManaged': bool(os.getenv('ADMIN_PASSWORD'))})


@api_view(['POST'])
def admin_claim(r):
    if User.objects.filter(role='admin').exists():
        return err('Administrator paroli allaqachon o‘rnatilgan.', 409)
    p = str(r.data.get('password', ''))
    if len(p) < 8:
        return err('Parol kamida 8 ta belgidan iborat bo‘lishi kerak.')
    u = User(username='admin', role='admin', full_name='Administrator', password_hash=make_password(p))
    u.save()
    return Response({'token': token_for(u), 'user': user_payload(u)})


@api_view(['POST'])
def admin_login(r):
    p = str(r.data.get('password', ''))
    u = User.objects.filter(role='admin', is_active=True).first()
    if not u or not check_password(p, u.password_hash):
        return err('Administrator paroli noto‘g‘ri.', 401)
    return Response({'token': token_for(u), 'user': user_payload(u)})


@api_view(['POST'])
def teacher_login(r):
    full = ' '.join(str(r.data.get('fullName', '')).split())
    cid = r.data.get('classId')
    sid = r.data.get('subjectId')
    try:
        cls = SchoolClass.objects.get(id=cid, is_active=True)
        subj = Subject.objects.get(id=sid, is_active=True)
    except Exception:
        return err('Tanlangan sinf yoki fan topilmadi.')
    if len(full) < 2:
        return err('Ismingizni kiriting.')
    u = User.objects.filter(role='teacher', full_name__iexact=full).first()
    if u and not u.is_active:
        return err('Hisobingiz bloklangan.', 403)
    if not u:
        parts = full.split()
        username = 'teacher_' + secrets.token_hex(5)
        u = User(username=username, role='teacher', full_name=full,
                 password_hash=make_password(secrets.token_urlsafe(24)))
        u.save()
        Teacher.objects.create(user=u, first_name=parts[0], last_name=' '.join(parts[1:]) or 'O‘qituvchi',
                               subject_names=[subj.name], assigned_classes=[cls.name])
    else:
        t = Teacher.objects.get(user=u)
        if subj.name not in t.subject_names:
            t.subject_names.append(subj.name)
        if cls.name not in t.assigned_classes:
            t.assigned_classes.append(cls.name)
        t.save()
    return Response({'token': token_for(u), 'user': user_payload(u)})


@api_view(['POST'])
def student_login(r):
    fn = str(r.data.get('firstName', '')).strip()
    ln = str(r.data.get('lastName', '')).strip()
    code = str(r.data.get('studentCode', '')).strip().upper()
    try:
        cls = SchoolClass.objects.get(id=r.data.get('classId'), is_active=True)
    except Exception:
        return err('Tanlangan sinf topilmadi.')
    if len(fn) < 2 or len(ln) < 2:
        return err('Ism va familiyani kiriting.')
    st = Student.objects.filter(student_code__iexact=code).first() if code else None
    if st and (st.first_name.lower() != fn.lower() or st.last_name.lower() != ln.lower()
               or st.school_class_id != cls.id):
        return err('O‘quvchi kodi boshqa o‘quvchiga tegishli.', 403)
    if not st:
        st = Student.objects.filter(first_name__iexact=fn, last_name__iexact=ln, school_class=cls).first()
    if st and code and st.student_code != code:
        return err('O‘z individual kodingizni kiriting yoki kod maydonini bo‘sh qoldiring.', 403)
    if not st:
        code = code or 'STS-' + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
        u = User(username='student_' + secrets.token_hex(6), role='student', full_name=fn + ' ' + ln,
                 password_hash=make_password(secrets.token_urlsafe(24)))
        u.save()
        st = Student.objects.create(user=u, first_name=fn, last_name=ln, school_class=cls, student_code=code)
    u = st.user
    return Response({'token': token_for(u), 'user': user_payload(u)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def auth_me(r):
    u = current_user(r)
    return Response({'user': user_payload(u)})


# ---------------------------------------------------------------- student
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def student_tests(r):
    u = actor(r, 'student')
    if not u:
        return err('Faqat o‘quvchi uchun.', 403)
    st = Student.objects.get(user=u)
    ts = Test.objects.filter(school_class=st.school_class, status__in=['active', 'scheduled']).select_related(
        'subject', 'teacher')
    return Response({'tests': [test_card(t, st) for t in ts if t.questions.exists()]})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_test(r, test_id):
    u = actor(r, 'student')
    if not u:
        return err('Ruxsat yo‘q.', 403)
    st = Student.objects.get(user=u)
    try:
        t = Test.objects.select_related('teacher', 'subject').get(id=test_id, school_class=st.school_class)
    except Exception:
        return err('Ushbu sinf uchun test topilmadi.', 404)
    if (t.status not in ['active', 'scheduled'] or (t.starts_at and t.starts_at > timezone.now())
            or (t.ends_at and t.ends_at < timezone.now())):
        return err('Test hozir faol emas.', 403)
    attempts = list(Attempt.objects.filter(test=t, student=st).order_by('-id'))
    a = next((x for x in attempts if x.status == 'in_progress' and x.expires_at > timezone.now()), None)
    if not a:
        if sum(1 for x in attempts if x.status != 'in_progress' or x.expires_at <= timezone.now()) >= t.max_attempts:
            return err('Urinishlar soni tugagan.', 403)
        a = Attempt.objects.create(test=t, student=st, attempt_number=len(attempts) + 1,
                                   expires_at=timezone.now() + timedelta(minutes=t.duration_minutes))
    questions = []
    saved = []
    for q in t.questions.prefetch_related('options').order_by('order_index', 'id'):
        questions.append({'id': q.id, 'orderIndex': q.order_index, 'questionType': q.question_type,
                          'questionText': q.question_text, 'points': q.points,
                          'options': [{'id': o.id, 'optionText': o.option_text, 'orderIndex': o.order_index}
                                      for o in q.options.all()]})
    for an in a.answers.all():
        saved.append({'questionId': an.question_id, 'selectedOptionIds': an.selected_option_ids,
                      'textAnswer': an.text_answer, 'isFlagged': an.is_flagged})
    return Response({
        'attemptId': a.id, 'expiresAt': a.expires_at, 'serverNow': timezone.now(),
        'test': {'id': t.id, 'title': t.title, 'description': t.description, 'subjectName': t.subject.name,
                 'teacherName': t.teacher.first_name + ' ' + t.teacher.last_name,
                 'durationMinutes': t.duration_minutes, 'questionCount': len(questions)},
        'questions': questions,
        'savedAnswers': {str(x['questionId']): {'selectedOptionIds': x['selectedOptionIds'],
                                                'textAnswer': x['textAnswer'],
                                                'isFlagged': x['isFlagged']} for x in saved}})


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def save_answer(r, attempt_id):
    u = actor(r, 'student')
    try:
        a = Attempt.objects.get(id=attempt_id, student__user=u)
    except Exception:
        return err('Urinishga kirish huquqi yo‘q.', 403)
    if a.status != 'in_progress':
        return err('Test yakunlangan.', 409)
    if a.expires_at + timedelta(seconds=10) < timezone.now():
        grade_attempt(a)
        return err('Ajratilgan vaqt tugadi.', 409)
    try:
        q = Question.objects.get(id=r.data.get('questionId'), test=a.test)
    except Exception:
        return err('Savol topilmadi.')
    ids = r.data.get('selectedOptionIds', [])
    ids = [int(x) for x in ids if str(x).isdigit()]
    StudentAnswer.objects.update_or_create(attempt=a, question=q, defaults={
        'selected_option_ids': ids, 'text_answer': str(r.data.get('textAnswer', ''))[:1000],
        'is_flagged': bool(r.data.get('isFlagged'))})
    return Response({'saved': True})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_attempt(r, attempt_id):
    u = actor(r, 'student')
    try:
        a = Attempt.objects.get(id=attempt_id, student__user=u)
    except Exception:
        return err('Urinish topilmadi.', 403)
    grade_attempt(a)
    result = TestResult.objects.get(attempt=a)
    return Response({'success': True, 'message': 'Test muvaffaqiyatli yakunlandi.',
                     'result': {'totalQuestions': result.total_questions, 'correctCount': result.correct_count,
                                'wrongCount': result.wrong_count, 'earnedPoints': result.earned_points,
                                'maxPoints': result.max_points, 'percentage': result.percentage,
                                'grade': result.grade, 'timeSpentSeconds': result.time_spent_seconds}})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def violation(r, attempt_id):
    u = actor(r, 'student')
    try:
        a = Attempt.objects.get(id=attempt_id, student__user=u)
    except Exception:
        return err('Urinish topilmadi.', 403)
    Violation.objects.create(attempt=a, test=a.test, student=a.student, teacher=a.test.teacher,
                             event_type=str(r.data.get('eventType', 'tab_hidden')),
                             details=str(r.data.get('details', ''))[:500])
    return Response({'saved': True})


# ---------------------------------------------------------------- teacher helpers
def teacher_required(r):
    u = actor(r, 'teacher')
    if not u:
        return None, None
    try:
        return u, Teacher.objects.get(user=u)
    except Teacher.DoesNotExist:
        return None, None


def test_json(t):
    return {'id': t.id, 'teacher_id': t.teacher_id, 'subject_id': t.subject_id, 'class_id': t.school_class_id,
            'title': t.title, 'description': t.description, 'duration_minutes': t.duration_minutes,
            'max_attempts': t.max_attempts, 'starts_at': t.starts_at, 'ends_at': t.ends_at,
            'status': t.status, 'subject_name': t.subject.name, 'class_name': t.school_class.name,
            'teacher_name': t.teacher.first_name + ' ' + t.teacher.last_name,
            'question_count': t.questions.count(),
            'submission_count': TestResult.objects.filter(test=t).count(), 'created_at': t.created_at}


def teacher_tests(r):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    return Response({'tests': [test_json(x) for x in Test.objects.filter(teacher=t).select_related(
        'subject', 'school_class', 'teacher').order_by('-created_at')]})


def teacher_test_detail(r, pk):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    try:
        x = Test.objects.get(id=pk, teacher=t)
    except Exception:
        return err('Test topilmadi.', 404)
    qs = []
    for q in x.questions.prefetch_related('options').order_by('order_index', 'id'):
        qs.append({'id': q.id, 'orderIndex': q.order_index, 'questionType': q.question_type,
                   'questionText': q.question_text, 'points': q.points,
                   'correctTextAnswer': q.correct_text_answer,
                   'options': [{'id': o.id, 'optionText': o.option_text, 'isCorrect': o.is_correct,
                                'orderIndex': o.order_index} for o in q.options.all()]})
    return Response({'test': test_json(x), 'questions': qs})


def save_test(r, pk=None):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    d = r.data
    try:
        subj = Subject.objects.get(id=d.get('subjectId'))
        cls = SchoolClass.objects.get(id=d.get('classId'))
    except Exception:
        return err('Fan yoki sinf topilmadi.')
    questions = d.get('questions', [])
    if not str(d.get('title', '')).strip() or not questions:
        return err('Test nomi va kamida bitta savol majburiy.')
    with transaction.atomic():
        if pk:
            try:
                x = Test.objects.get(id=pk, teacher=t)
            except Exception:
                return err('Test topilmadi.', 404)
        else:
            x = Test(teacher=t)
        x.subject = subj
        x.school_class = cls
        x.title = str(d['title'])[:200]
        x.description = str(d.get('description', ''))[:1000]
        x.duration_minutes = max(1, min(300, int(d.get('durationMinutes') or 30)))
        x.max_attempts = max(1, min(20, int(d.get('maxAttempts') or 1)))
        x.status = d.get('status') if d.get('status') in ['draft', 'scheduled', 'active'] else 'draft'
        x.starts_at = d.get('startsAt') or None
        x.ends_at = d.get('endsAt') or None
        x.save()
        x.questions.all().delete()
        for i, q in enumerate(questions):
            qq = Question.objects.create(test=x, order_index=i, question_type=q.get('questionType', 'single_choice'),
                                         question_text=str(q.get('questionText', '')),
                                         points=max(1, int(q.get('points', 1))),
                                         correct_text_answer=str(q.get('correctTextAnswer', '')))
            for j, o in enumerate(q.get('options', [])):
                AnswerOption.objects.create(question=qq, option_text=str(o.get('optionText', '')),
                                            is_correct=bool(o.get('isCorrect')), order_index=j)
    return Response({'testId': x.id})


def _dash_payload(t):
    tests = Test.objects.filter(teacher=t)
    results = TestResult.objects.filter(teacher=t)
    avg = round(results.aggregate(v=Avg('percentage'))['v'] or 0, 1)
    participants = results.values('student').distinct().count()
    class_stats = []
    for row in results.values('school_class__name').annotate(avg=Avg('percentage'), cnt=Count('id')):
        a = round(row['avg'] or 0, 1)
        class_stats.append({'class_name': row['school_class__name'], 'avg_percentage': a,
                            'submissions': row['cnt']})
    grades = [{'grade': g, 'count': results.filter(grade=g).count()} for g in ['5', '4', '3', '2']]
    return {
        'stats': {'totalTests': tests.count(), 'activeTests': tests.filter(status='active').count(),
                  'archivedTests': tests.filter(status='archived').count(),
                  'finishedTests': results.values('test').distinct().count(),
                  'totalStudents': participants, 'totalParticipants': participants,
                  'totalSubmissions': results.count(), 'averagePercentage': avg, 'avgPercentage': avg},
        'recentTests': [test_json(x) for x in tests.select_related('subject', 'school_class', 'teacher').order_by(
            '-created_at')[:5]],
        'classStats': class_stats,
        'gradeDistribution': grades,
    }


# ---------------------------------------------------------------- teacher endpoints
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_meta(r):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    return Response({
        'teacher': user_payload(u),
        'classes': list(SchoolClass.objects.filter(is_active=True).values('id', 'name', 'grade_level', 'section')),
        'subjects': list(Subject.objects.filter(is_active=True).values('id', 'name', 'description')),
        'schoolName': Setting.objects.get(key='school_name').value})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_dashboard(r):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    return Response(_dash_payload(t))


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_stats(r):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    data = _dash_payload(t)
    test_stats = []
    for x in Test.objects.filter(teacher=t).select_related('subject', 'school_class'):
        rs = TestResult.objects.filter(test=x)
        agg = rs.aggregate(a=Avg('percentage'), mn=Min('percentage'), mx=Max('percentage'))
        test_stats.append({
            'id': x.id,
            'title': x.title,
            'subject_name': x.subject.name,
            'class_name': x.school_class.name,
            'submissions': rs.count(),
            'avg_percentage': round(agg['a'] or 0, 1),
            'min_percentage': agg['mn'],
            'max_percentage': agg['mx'],
            'grade_5': rs.filter(grade='5').count(),
            'grade_4': rs.filter(grade='4').count(),
            'grade_3': rs.filter(grade='3').count(),
            'grade_2': rs.filter(grade='2').count(),
        })
    qa = []
    for row in StudentAnswer.objects.filter(question__test__teacher=t).values(
            'question_id', 'question__question_text', 'question__test__title').annotate(
            total=Count('id'), correct=Count('id', filter=Q(is_correct=True))):
        qa.append({'id': row['question_id'],
                   'question_text': row['question__question_text'],
                   'test_title': row['question__test__title'],
                   'total_answers': row['total'],
                   'correct_answers': row['correct']})
    qa.sort(key=lambda x: (x['correct_answers'] / x['total_answers']) if x['total_answers'] else 1)
    data['testStats'] = test_stats
    data['questionAccuracy'] = qa
    return Response(data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_tests_list(r):
    return teacher_tests(r)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def teacher_tests_root(r):
    return teacher_tests(r) if r.method == 'GET' else save_test(r)


@api_view(['GET', 'PUT', 'DELETE', 'PATCH'])
@permission_classes([IsAuthenticated])
def teacher_test_item(r, pk):
    if r.method == 'GET':
        return teacher_test_detail(r, pk)
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    try:
        x = Test.objects.get(id=pk, teacher=t)
    except Exception:
        return err('Test topilmadi.', 404)
    if r.method == 'PUT':
        return save_test(r, pk)
    if r.method == 'DELETE':
        x.delete()
        return Response({'deleted': True})
    x.status = r.data.get('status', x.status)
    x.save()
    return Response({'updated': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_results(r):
    u, t = teacher_required(r)
    if not u or not t:
        return err('Ruxsat yo‘q.', 403)

    rows = (
        TestResult.objects
        .filter(teacher=t)
        .select_related(
            'student',
            'school_class',
            'test',
            'test__subject',
            'attempt',
        )
        .annotate(violation_count=Count('attempt__violation'))
    )

    # Eski va yangi frontend parametr nomlarini qo‘llab-quvvatlaymiz.
    filter_specs = (
        (('classId', 'class_id'), 'school_class_id', 'Sinf'),
        (('subjectId', 'subject_id'), 'test__subject_id', 'Fan'),
        (('testId', 'test_id'), 'test_id', 'Test'),
    )

    for param_names, model_field, label in filter_specs:
        raw_value = None
        for param_name in param_names:
            if param_name in r.query_params:
                raw_value = r.query_params.get(param_name)
                break

        if raw_value is None:
            continue

        raw_value = str(raw_value).strip()
        if raw_value.lower() in ('', 'all', 'none', 'null', 'undefined'):
            continue

        try:
            filter_id = int(raw_value)
        except (TypeError, ValueError):
            return err(f'{label} filtri uchun ID butun son bo‘lishi kerak.')

        if filter_id <= 0:
            return err(f'{label} filtri uchun ID musbat bo‘lishi kerak.')

        rows = rows.filter(**{model_field: filter_id})

    rows = rows.order_by('-submitted_at', '-id')

    result_items = []
    for x in rows:
        result_items.append({
            'id': x.id,
            'attempt_id': x.attempt_id,
            'test_id': x.test_id,
            'student_id': x.student_id,
            'total_questions': x.total_questions,
            'correct_count': x.correct_count,
            'wrong_count': x.wrong_count,
            'earned_points': x.earned_points,
            'max_points': x.max_points,
            'percentage': x.percentage,
            'grade': x.grade,
            'time_spent_seconds': x.time_spent_seconds,
            'submitted_at': x.submitted_at,
            'started_at': x.attempt.started_at,
            'first_name': x.student.first_name,
            'last_name': x.student.last_name,
            'student_code': x.student.student_code,
            'class_id': x.school_class_id,
            'class_name': x.school_class.name,
            'test_title': x.test.title,
            'subject_id': x.test.subject_id,
            'subject_name': x.test.subject.name,
            'violation_count': x.violation_count,
            'is_terminated': x.is_terminated,
            'attempt_status': x.attempt.status,
        })

    return Response({'results': result_items})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def teacher_result_update(r, pk):
    u, t = teacher_required(r)
    if not u or not t:
        return err('Faqat tizimga kirgan o‘qituvchi uchun.', 403)

    # Boshqa o‘qituvchining natijasi hech qachon query'dan olinmaydi.
    try:
        with transaction.atomic():
            result = (
                TestResult.objects
                .select_for_update()
                .select_related('student', 'test', 'school_class')
                .get(pk=pk, teacher=t)
            )

            old_values = {
                'correct_count': result.correct_count,
                'wrong_count': result.wrong_count,
                'percentage': result.percentage,
                'grade': result.grade,
                'earned_points': result.earned_points,
            }

            data = r.data

            correct_count = result.correct_count
            if 'correct_count' in data:
                raw_correct = data.get('correct_count')
                if isinstance(raw_correct, bool):
                    return err('To‘g‘ri javoblar soni butun son bo‘lishi kerak.')
                try:
                    correct_count = int(raw_correct)
                except (TypeError, ValueError, OverflowError):
                    return err('To‘g‘ri javoblar soni butun son bo‘lishi kerak.')

                if str(raw_correct).strip() != str(correct_count):
                    return err('To‘g‘ri javoblar soni butun son bo‘lishi kerak.')
                if not 0 <= correct_count <= result.total_questions:
                    return err(
                        f'To‘g‘ri javoblar soni 0 dan {result.total_questions} gacha bo‘lishi kerak.'
                    )

            percentage = Decimal(str(result.percentage))
            if 'percentage' in data:
                try:
                    percentage = Decimal(str(data.get('percentage')))
                except (InvalidOperation, TypeError, ValueError):
                    return err('Foiz son bo‘lishi kerak.')

                if not percentage.is_finite() or percentage < 0 or percentage > 100:
                    return err('Foiz 0 dan 100 gacha bo‘lishi kerak.')

            raw_grade = data.get('grade', None)
            if raw_grade in (None, ''):
                grade = (
                    '5' if percentage >= Decimal('86') else
                    '4' if percentage >= Decimal('71') else
                    '3' if percentage >= Decimal('56') else
                    '2'
                )
            else:
                grade = str(raw_grade).strip()
                if grade not in ('2', '3', '4', '5'):
                    return err('Baho faqat 2, 3, 4 yoki 5 bo‘lishi mumkin.')

            percentage_value = float(percentage.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP))
            earned_points = int(
                (Decimal(result.max_points) * Decimal(str(percentage_value)) / Decimal('100'))
                .quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            )

            result.correct_count = correct_count
            result.wrong_count = result.total_questions - correct_count
            result.percentage = percentage_value
            result.grade = grade
            result.earned_points = earned_points
            result.save(update_fields=[
                'correct_count',
                'wrong_count',
                'percentage',
                'grade',
                'earned_points',
            ])

            new_values = {
                'correct_count': result.correct_count,
                'wrong_count': result.wrong_count,
                'percentage': result.percentage,
                'grade': result.grade,
                'earned_points': result.earned_points,
            }

            if old_values != new_values:
                Activity.objects.create(
                    actor_role='teacher',
                    actor_name=u.full_name,
                    action='O‘quvchi test natijasi qo‘lda tahrirlandi',
                    target_type='TestResult',
                    target_id=str(result.id),
                    details=json.dumps({
                        'result_id': result.id,
                        'student_id': result.student_id,
                        'student_name': f'{result.student.first_name} {result.student.last_name}',
                        'test_id': result.test_id,
                        'test_title': result.test.title,
                        'old': old_values,
                        'new': new_values,
                        'note': (
                            'Bu qo‘lda kiritilgan natija tuzatishidir. '
                            'StudentAnswer yozuvlari o‘zgartirilmagan.'
                        ),
                    }, ensure_ascii=False, default=str),
                )

    except TestResult.DoesNotExist:
        # 404 javobi boshqa o‘qituvchining natijasi borligini ham oshkor qilmaydi.
        return err('Natija topilmadi yoki sizga tegishli emas.', 404)

    return Response({
        'updated': True,
        'result': {
            'id': result.id,
            'correct_count': result.correct_count,
            'wrong_count': result.wrong_count,
            'percentage': result.percentage,
            'grade': result.grade,
            'earned_points': result.earned_points,
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def teacher_violations(r):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    return Response({'violations': [{
        'id': v.id, 'attempt_id': v.attempt_id, 'test_id': v.test_id, 'student_id': v.student_id,
        'teacher_id': v.teacher_id, 'event_type': v.event_type, 'details': v.details,
        'occurred_at': v.occurred_at, 'reviewed_by_teacher': v.reviewed_by_teacher,
        'first_name': v.student.first_name, 'last_name': v.student.last_name,
        'student_code': v.student.student_code, 'class_name': v.student.school_class.name,
        'test_title': v.test.title} for v in Violation.objects.filter(teacher=t).select_related(
        'student', 'test').order_by('-occurred_at')]})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def review_violation(r, pk):
    u, t = teacher_required(r)
    if not u:
        return err('Ruxsat yo‘q.', 403)
    Violation.objects.filter(id=pk, teacher=t).update(reviewed_by_teacher=True)
    return Response({'updated': True})


@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def teacher_profile(r):
    u, t = teacher_required(r)
    if not u or not t:
        return err('Ruxsat yo‘q.', 403)

    first_name = str(r.data.get('firstName', t.first_name)).strip()
    last_name = str(r.data.get('lastName', t.last_name)).strip()
    bio = str(r.data.get('bio', t.bio)).strip()
    phone = str(r.data.get('phone', t.phone)).strip()

    if len(first_name) < 2 or len(last_name) < 2:
        return err('Ism va familiya kamida 2 ta belgidan iborat bo‘lishi kerak.')

    current_password = str(r.data.get('currentPassword') or '')
    new_password = str(r.data.get('newPassword') or '')

    if current_password or new_password:
        if not current_password or not new_password:
            return err('Parolni almashtirish uchun joriy va yangi parolni kiriting.')
        if not check_password(current_password, u.password_hash):
            return err('Joriy parol noto‘g‘ri.', 403)
        if len(new_password) < 8:
            return err('Yangi parol kamida 8 ta belgidan iborat bo‘lishi kerak.')

    old_profile = {
        'first_name': t.first_name,
        'last_name': t.last_name,
        'phone': t.phone,
        'bio': t.bio,
        'password_changed': False,
    }

    with transaction.atomic():
        t.first_name = first_name
        t.last_name = last_name
        t.phone = phone
        t.bio = bio
        t.save(update_fields=['first_name', 'last_name', 'phone', 'bio'])

        u.full_name = f'{first_name} {last_name}'.strip()
        if new_password:
            u.password_hash = make_password(new_password)
            old_profile['password_changed'] = True
        u.save(update_fields=['full_name', 'password_hash'])

        new_profile = {
            'first_name': t.first_name,
            'last_name': t.last_name,
            'phone': t.phone,
            'bio': t.bio,
            'password_changed': bool(new_password),
        }

        if old_profile != new_profile:
            Activity.objects.create(
                actor_role='teacher',
                actor_name=u.full_name,
                action='O‘qituvchi profilini yangiladi',
                target_type='Teacher',
                target_id=str(t.id),
                details=json.dumps({
                    'old': old_profile,
                    'new': new_profile,
                }, ensure_ascii=False),
            )

    return Response({
        'success': True,
        'saved': True,
        'fullName': u.full_name,
        'firstName': t.first_name,
        'lastName': t.last_name,
        'phone': t.phone,
        'bio': t.bio,
    })


# ---------------------------------------------------------------- admin
def admin_guard(r):
    return actor(r, 'admin')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_dashboard(r):
    if not actor(r, 'admin'):
        return err('Ruxsat yo‘q.', 403)
    return Response({
        'stats': {'teachers': Teacher.objects.count(), 'tests': Test.objects.count(),
                  'activeTests': Test.objects.filter(status='active').count(),
                  'students': Student.objects.count(), 'submissions': TestResult.objects.count()},
        'testsBySubject': [{'subject_name': s.name, 'test_count': Test.objects.filter(subject=s).count()}
                           for s in Subject.objects.all()],
        'recentActivity': list(Activity.objects.order_by('-created_at').values()[:20])})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def admin_teachers(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    if r.method == 'POST':
        d = r.data
        full = str(d.get('fullName', d.get('full_name', 'O‘qituvchi')))
        parts = full.split()
        u = User(username=str(d.get('username') or 'teacher_' + secrets.token_hex(4)), role='teacher',
                 full_name=full, password_hash=make_password(str(d.get('password') or secrets.token_urlsafe(16))))
        u.save()
        t = Teacher.objects.create(user=u, first_name=parts[0], last_name=' '.join(parts[1:]) or 'O‘qituvchi')
        return Response({'id': t.id})
    return Response({'teachers': [{
        'id': t.id, 'fullName': t.first_name + ' ' + t.last_name, 'username': t.user.username,
        'subjectNames': t.subject_names, 'assignedClasses': t.assigned_classes,
        'testCount': Test.objects.filter(teacher=t).count(), 'isActive': t.user.is_active}
        for t in Teacher.objects.select_related('user')]})


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_teacher_item(r, pk):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    try:
        t = Teacher.objects.select_related('user').get(id=pk)
    except Exception:
        return err('O‘qituvchi topilmadi.', 404)
    if r.method == 'DELETE':
        t.user.delete()
        return Response({'deleted': True})
    t.first_name = r.data.get('firstName', t.first_name)
    t.last_name = r.data.get('lastName', t.last_name)
    t.user.is_active = bool(r.data.get('isActive', t.user.is_active))
    t.user.save()
    t.save()
    return Response({'saved': True})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def admin_classes(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    if r.method == 'POST':
        d = r.data
        name = str(d.get('name', '')).strip()
        SchoolClass.objects.create(name=name, grade_level=int(d.get('gradeLevel', 1)),
                                   section=str(d.get('section', 'A')))
        return Response({'created': True})
    return Response({'classes': [{
        'id': c.id, 'name': c.name, 'grade_level': c.grade_level, 'section': c.section,
        'is_active': c.is_active, 'student_count': Student.objects.filter(school_class=c).count(),
        'test_count': Test.objects.filter(school_class=c).count()} for c in SchoolClass.objects.all()]})


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_class_item(r, pk):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    try:
        c = SchoolClass.objects.get(id=pk)
    except Exception:
        return err('Sinf topilmadi.', 404)
    if r.method == 'DELETE':
        c.is_active = False
        c.save()
        return Response({'deleted': True})
    c.name = r.data.get('name', c.name)
    c.grade_level = r.data.get('gradeLevel', c.grade_level)
    c.section = r.data.get('section', c.section)
    c.is_active = r.data.get('isActive', c.is_active)
    c.save()
    return Response({'saved': True})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def admin_subjects(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    if r.method == 'POST':
        Subject.objects.create(name=str(r.data.get('name', '')).strip(),
                               description=str(r.data.get('description', '')))
        return Response({'created': True})
    return Response({'subjects': [{
        'id': s.id, 'name': s.name, 'description': s.description, 'is_active': s.is_active,
        'test_count': Test.objects.filter(subject=s).count()} for s in Subject.objects.all()]})


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_subject_item(r, pk):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    try:
        s = Subject.objects.get(id=pk)
    except Exception:
        return err('Fan topilmadi.', 404)
    if r.method == 'DELETE':
        s.is_active = False
        s.save()
        return Response({'deleted': True})
    s.name = r.data.get('name', s.name)
    s.description = r.data.get('description', s.description)
    s.is_active = r.data.get('isActive', s.is_active)
    s.save()
    return Response({'saved': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_tests(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    return Response({'tests': [test_json(t) for t in Test.objects.select_related(
        'subject', 'school_class', 'teacher')]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_results(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    return Response({'results': [{
        'id': x.id, 'test_title': x.test.title, 'first_name': x.student.first_name,
        'last_name': x.student.last_name, 'class_name': x.school_class.name,
        'subject_name': x.test.subject.name, 'percentage': x.percentage, 'grade': x.grade,
        'submitted_at': x.submitted_at, 'correct_count': x.correct_count, 'wrong_count': x.wrong_count}
        for x in TestResult.objects.select_related('test', 'student', 'school_class')]})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_students(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    return Response({'students': [{
        'id': s.id, 'first_name': s.first_name, 'last_name': s.last_name, 'student_code': s.student_code,
        'class_id': s.school_class_id, 'class_name': s.school_class.name}
        for s in Student.objects.select_related('school_class')]})


@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_student_item(r, pk):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    try:
        s = Student.objects.get(id=pk)
    except Exception:
        return err('O‘quvchi topilmadi.', 404)
    if r.method == 'DELETE':
        s.user.delete()
        return Response({'deleted': True})
    s.first_name = r.data.get('firstName', s.first_name)
    s.last_name = r.data.get('lastName', s.last_name)
    s.save()
    return Response({'saved': True})


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def admin_test_item(r, pk):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    try:
        t = Test.objects.get(id=pk)
    except Exception:
        return err('Test topilmadi.', 404)
    if r.method == 'DELETE':
        t.delete()
        return Response({'deleted': True})
    t.status = r.data.get('status', t.status)
    t.save()
    return Response({'saved': True})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_activity(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    return Response({'activityLogs': list(Activity.objects.order_by('-created_at').values()[:100]),
                     'violationLogs': list(Violation.objects.order_by('-occurred_at').values()[:100])})


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def admin_settings(r):
    if not admin_guard(r):
        return err('Ruxsat yo‘q.', 403)
    if r.method == 'PUT':
        Setting.objects.update_or_create(
            key='school_name', defaults={'value': str(r.data.get('schoolName', 'SCHOOL TEST SYSTEM'))})
        p = r.data.get('newPassword')
        if p:
            u = User.objects.filter(role='admin').first()
            if u:
                u.password_hash = make_password(str(p))
                u.save()
        return Response({'saved': True})
    return Response({
        'schoolName': Setting.objects.get_or_create(key='school_name',
                                                    defaults={'value': 'SCHOOL TEST SYSTEM'})[0].value,
        'envManagedPassword': bool(os.getenv('ADMIN_PASSWORD'))})