FROM python:3.13-slim

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -e libs/domain -e services/asco -e services/audit

CMD ["python", "-c", "import ubunturemit_audit; print('Audit Service ready')"]
