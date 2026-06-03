web: python manage.py migrate --noinput && python manage.py ensure_superuser && python manage.py collectstatic --noinput && gunicorn intranet.wsgi --log-file - --timeout 120 --workers 2
