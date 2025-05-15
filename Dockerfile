FROM andarguy/camoufox:latest
COPY . /app
WORKDIR /app
RUN mkdir -p /app/auth_cache
VOLUME /app/auth_cache
RUN pip install -r requirements.txt
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8015", "--workers", "4"]
