FROM public.ecr.aws/docker/library/python:3.13-slim

ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .

EXPOSE 8080
CMD ["python", "app.py"]
