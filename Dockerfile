FROM python:3.13-slim
WORKDIR /bot
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN gcc -O3 -shared -fPIC -static-libgcc optimization/c4_engine.c -o optimization/c4_engine.so
COPY logo.png /logo.png
COPY logo.jpg /logo.jpg
# -u: unbuffered stdout, so every answer reaches the arena immediately
CMD ["python", "-u", "main.py"]
