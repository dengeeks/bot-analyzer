FROM python:3.11-slim-bullseye

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN apt-get update

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . /app
