import os
import time
import threading
from dotenv import load_dotenv
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json5
import re

def load_api_keys():
    load_dotenv()
    api_keys = []
    env_keys = os.getenv("API_KEYS")
    if env_keys:
        api_keys = [k.strip() for k in env_keys.split(",") if k.strip()]
    elif os.path.exists("keys.txt"):
        with open("keys.txt", "r", encoding="utf-8") as f:
            api_keys = [line.strip() for line in f if line.strip()]
    if not api_keys:
        raise RuntimeError("🚫 Không tìm thấy API key!")
    return api_keys

class GeminiKeyManager:
    def __init__(self, model_name = None, logger=print, rpm_limit=8):
        self.api_keys = load_api_keys()
        self.current_index = 0
        self.model_name = model_name or "gemini-2.0-flash-lite-preview-02-05"
        self.logger = logger
        self.lock = threading.Lock()
        
        # --- Cấu hình Rate Limiting ---
        self.rpm_limit = rpm_limit
        self.request_timestamps = [] # Lưu vết thời gian các request trong 60s
        self.last_request_start = 0  # Thời điểm bắt đầu request gần nhất
        self.request_spacing = 3     # Giãn cách 3 giây giữa các lần gọi (start)
        
        self.set_api_key(0)

    def log(self, msg):
        if self.logger: self.logger(msg)
        else: print(msg)

    def set_api_key(self, index):
        with self.lock:
            self.current_index = index % len(self.api_keys)
            genai.configure(api_key=self.api_keys[self.current_index])
            # self.log(f"🔑 Đang dùng key {self.current_index + 1}/{len(self.api_keys)}")

    def _wait_for_rate_limit(self):
        """Hàm điều phối luồng: Chờ nếu vi phạm RPM hoặc giãn cách giây"""
        while True:
            with self.lock:
                now = time.time()
                
                # 1. Dọn dẹp các timestamp cũ hơn 60 giây
                self.request_timestamps = [t for t in self.request_timestamps if now - t < 60]
                
                # 2. Kiểm tra giới hạn RPM
                if len(self.request_timestamps) >= self.rpm_limit:
                    wait_time = 60 - (now - self.request_timestamps[0])
                    if wait_time > 0:
                        self.log(f"⏳ Đạt ngưỡng {self.rpm_limit} RPM. Nghỉ {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue # Kiểm tra lại sau khi nghỉ
                
                # 3. Kiểm tra giãn cách giữa các lần khởi chạy (2-3 giây)
                time_since_last = now - self.last_request_start
                if time_since_last < self.request_spacing:
                    wait_gap = self.request_spacing - time_since_last
                    time.sleep(wait_gap)
                    continue
                
                # Nếu thỏa mãn mọi điều kiện: Chốt thời gian và cho phép chạy
                self.last_request_start = time.time()
                self.request_timestamps.append(self.last_request_start)
                break

    def generate(self, prompt, retries=10):
        attempt = 0

        while attempt < retries:
            # Điều phối lưu lượng trước khi gọi API
            self._wait_for_rate_limit()

            with self.lock:
                api_key = self.api_keys[self.current_index]
                current_key_num = self.current_index + 1
                self.current_index = (self.current_index + 1) % len(self.api_keys)

            try:
                attempt_start = time.perf_counter()

                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(self.model_name)

                self.log(f"🚀 CALL API | Key {current_key_num}")

                response = model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        response_mime_type="application/json",
                        response_schema={
                            "type": "object",
                            "properties": {
                                "chapter_number": {"type": "integer"},
                                "chapter_title": {"type": "string"},
                                "chapter_content": {"type": "string"},
                                "other_content": {"type": "string"}
                            },
                            "required": ["chapter_number", "chapter_title", "chapter_content", "other_content"]
                        },
                        max_output_tokens=8192,
                    )
                )

                attempt_end = time.perf_counter()
                self.log(f"⏱ Key {current_key_num} | Time: {attempt_end - attempt_start:.2f}s")

                return response

            except Exception as e:
                err = str(e)
                attempt += 1

                # 🔥 503: đổi key + nghỉ ngắn
                if "503" in err or "ServiceUnavailable" in err:
                    self.log(f"⚠️ Key {current_key_num} bị 503 → đổi key, nghỉ 5s")
                    time.sleep(30)
                    continue

                # 🔥 429: nghỉ lâu hơn
                elif "429" in err or "limit" in err.lower():
                    self.log(f"⚠️ Key {current_key_num} rate limit → nghỉ 10s")
                    time.sleep(45)
                    continue

                # 🔥 lỗi khác
                else:
                    self.log(f"❌ Lỗi API (Key {current_key_num}): {e}")
                    time.sleep(2)
                    continue

        self.log("💀 Hết retry, bỏ request")
        return None
