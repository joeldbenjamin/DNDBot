FROM python:3.13
WORKDIR /Discord
COPY requirements.txt /Discord
RUN pip install -r requirements.txt
COPY . /Discord
CMD python bot.py