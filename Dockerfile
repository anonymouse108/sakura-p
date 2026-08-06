FROM python:3.12-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD gunicorn --bind 0.0.0.0:$3000 --workers 2 --threads 4 app:app
