FROM python:3.6-slim-stretch

RUN apt update
RUN apt install -y python3-dev gcc

ADD frontend frontend/
ADD app.py .
ADD templates templates/
ADD requirements.txt .

RUN pip install -r requirements.txt

EXPOSE 8011

CMD ["python", "app.py"]
