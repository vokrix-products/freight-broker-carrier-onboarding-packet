FROM python:3.12-slim
ARG CACHEBUST=1
WORKDIR /app

# Docling pulls OpenCV + torch. slim has neither the GL nor glib libs they need.
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt --quiet
COPY . .
CMD ["python3", "poller.py"]
