FROM python:3.12-slim

WORKDIR /app

# 安装系统依赖（pymupdf、pillow 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 创建数据目录
RUN mkdir -p data/rules data/uploads data/exports data/audit_history

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
