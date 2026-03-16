FROM python:3.11-slim

WORKDIR /Discord

COPY requirements.txt /Discord
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY . /Discord

CMD ["python", "bot.py"]