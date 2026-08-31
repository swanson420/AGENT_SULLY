FROM python:3.11-slim

WORKDIR /app

COPY negotiation-agent-current/requirements.txt negotiation-agent-current/requirements.txt
RUN pip install --no-cache-dir -r negotiation-agent-current/requirements.txt \
    && pip install --no-cache-dir fastapi "uvicorn[standard]" google-adk

COPY negotiation-agent-current negotiation-agent-current
COPY submission-pack submission-pack

WORKDIR /app/negotiation-agent-current
ENV PYTHONPATH=/app/negotiation-agent-current
ENV PORT=8080
EXPOSE 8080

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
