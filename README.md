# School Test System — Django Backend

Bu backend yuklangan React/TypeScript maktab test frontendining API yo‘llari va JSON formatlariga moslab yozilgan. Backend alohida papkada; Vercel frontend, Render backend, PostgreSQL ma’lumotlar bazasi.

## Muhim imkoniyatlar
- Admin, o‘qituvchi va o‘quvchi rollari; Bearer JWT avtorizatsiya.
- Sinf, fan, test, savol, variant, urinish, javob, natija va nazorat hodisalari PostgreSQL’da saqlanadi.
- O‘quvchi boshqa qurilmadan shu ism/familiya/sinf va individual kod bilan qayta kirsa, serverdagi `in_progress` urinishini topib davom ettiradi. Javoblar har safar server bazasiga yoziladi.
- To‘g‘ri javoblar o‘quvchi testni ishlayotgan vaqtda API’dan berilmaydi; baholash serverda bajariladi.
- Test va natijalar qurilmaga emas, serverdagi umumiy bazaga bog‘langan.

## Lokal ishga tushirish
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows; Linux: cp .env.example .env
python manage.py migrate --run-syncdb
python manage.py runserver
```
API: `http://127.0.0.1:8000/api/`

## Render deploy
1. Ushbu papkani alohida GitHub repositoryga yuklang (yoki mavjud repo ichida backend root sifatida alohida deploy qiling).
2. Render’da **New → Blueprint** qilib `render.yaml` ni tanlang. Yoki Web Service yarating: Build `./build.sh`, Start `gunicorn config.wsgi:application`.
3. Render PostgreSQL yarating va `DATABASE_URL` ni Internal Database URL bilan ulang.
4. Environment: `SECRET_KEY` (uzun tasodifiy qiymat), `DEBUG=false`, `ALLOWED_HOSTS=.onrender.com`, `CORS_ALLOWED_ORIGINS=https://SIZNING-LOYIHA.vercel.app`, `ADMIN_USERNAME`, `ADMIN_PASSWORD`.
5. Deploy tugagach `https://BACKEND.onrender.com/api/public/bootstrap` ochilib JSON qaytarishini tekshiring.

## Frontend Vercel ulanishi
Frontend papkasidagi `src/lib/api.ts` faylida fetch URL’ini backend manziliga yo‘naltiring. Tavsiya etilgan o‘zgarish:
```ts
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\\/$/, '');
// apiRequest ichida fetch(url, ...) o‘rniga:
const response = await fetch(`${API_BASE_URL}${url}`, { ...options, headers });
```
Vercel Environment Variables’da `VITE_API_BASE_URL=https://BACKEND.onrender.com` qo‘ying va qayta deploy qiling. `api.ts` faylining to‘liq tayyor varianti `frontend-api.ts.example` faylida.

## Bir nechta qurilmada testni davom ettirish
O‘quvchi 1-qurilmada testga kiradi. U `ism + familiya + sinf + studentCode` orqali tizimga kirgan bo‘lishi kerak. 2-qurilmada aynan shu ma’lumotlar bilan login qiladi. `POST /api/student/tests/{id}/start` mavjud, tugamagan urinishni qaytaradi; oldin saqlangan javoblar `savedAnswers` sifatida keladi. Kodni yo‘qotmaslik kerak: birinchi kirishda qaytarilgan `studentCode` ni o‘quvchiga ko‘rsating va saqlab qo‘ying.

## Eslatma
Bu paket API va ma’lumotlar qatlamini beradi; frontendning vizual qismini o‘zgartirmaydi. Ishga tushirishdan oldin Render’dagi CORS domenini aniq Vercel domeniga almashtiring. Production’da HTTPS ishlating va `ADMIN_PASSWORD` uchun kuchli maxfiy qiymat belgilang.
