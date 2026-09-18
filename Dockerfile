FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agentuse/ agentuse/
COPY static/ static/
COPY run.py .

ENV AGENTUSE_HOST=0.0.0.0
ENV AGENTUSE_PORT=8000
EXPOSE 8000
VOLUME ["/app/data"]

CMD ["python", "run.py"]
