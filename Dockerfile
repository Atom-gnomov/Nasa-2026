# Lunar Mission Builder — образ для хостингу (I3). Збирання: docker build -t lunar-mission-builder .
# Запуск:   docker run -p 8000:8000 -v lse-data:/data lunar-mission-builder
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LSE_CACHE_DIR=/data \
    PORT=8000

WORKDIR /srv

# Залежності окремим шаром: змінюється рідко (ефемериди DE440 ≈ 114 МБ)
COPY requirements.txt requirements-prod.txt ./
RUN pip install -r requirements.txt -r requirements-prod.txt

# Код: застосунок і скрипти підготовки даних (tools/ запускає автопідготовка з app/services/bootstrap.py)
COPY app ./app
COPY tools ./tools
COPY pyproject.toml ./

# Дані NASA (температура, глобус, 3D) — у томі /data, щоб переживали перезапуск і оновлення образу
RUN useradd --create-home --uid 10001 lse && mkdir -p /data && chown -R lse:lse /data /srv
USER lse
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/api/meta' % os.environ.get('PORT','8000'), timeout=4)"

# Зоряна карта (NASA SVS «Deep Star Maps 2020», 2,8 МБ) лежить в образі й копіюється в /data/starmap, якщо там ще немає
# своєї (cp -n не перезаписує). Без неї небо — лише CSS-тло.
# WEB_CONCURRENCY — кількість воркерів (за замовчуванням 2); тяжкі запити (/api/search) тримають воркер до кількох секунд,
# тому таймаут більший за типовий. gthread: поки один запит рахується, воркер приймає легкі (статика, /api/meta).
CMD ["sh", "-c", "mkdir -p /data/starmap && cp -n /srv/app/data/starmap/* /data/starmap/; exec gunicorn --bind 0.0.0.0:${PORT} --workers ${WEB_CONCURRENCY:-2} --threads 4 --timeout 120 --access-logfile - 'app:create_app()'"]
