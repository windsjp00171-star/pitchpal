FROM python:3.11-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 即時輸出 log（否則 "Running on local URL" 等 stdout 訊息會被緩衝看不到）
# 並關閉 gradio 5.x 預設 SSR（slim 鏡像無 Node 環境會啟動卡死）
ENV PYTHONUNBUFFERED=1 \
    GRADIO_SSR_MODE=False

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

EXPOSE 7860

CMD ["python", "app.py"]
