FROM python:3.13-slim
WORKDIR /bot
RUN pip install --no-cache-dir "openai>=3,<4"
COPY main.py .
# -u: unbuffered stdout, so every answer reaches the arena immediately
CMD ["python", "-u", "main.py"]
