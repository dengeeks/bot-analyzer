FROM python:3.11

WORKDIR /app

COPY requirements.txt /app/requirements.txt

# Обновляем pip и устанавливаем Python-зависимости (включая selenium)
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Устанавливаем Chromium и ChromeDriver
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

COPY . /app