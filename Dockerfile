FROM python:3.11

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN apt-get update

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

RUN playwright install chromium
RUN playwright install-deps chromium

COPY . /app
