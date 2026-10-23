FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 MPLBACKEND=Agg
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# data/ vive en un volumen montado en /app/data (usuarios, keys, tokens, análisis)
RUN mkdir -p /app/data/users
EXPOSE 8000
CMD ["sh", "-c", "uvicorn apex_app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
