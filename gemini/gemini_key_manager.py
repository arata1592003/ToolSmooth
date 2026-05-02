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
    def __init__(self, model_name = None, logger=print):
        self.api_keys = load_api_keys()
        self.current_index = 0
        self.model_name = model_name or "gemini-2.5-flash"
        self.logger = logger
        self.lock = threading.Lock()
        self.set_api_key(0)

    def log(self, msg):
        if self.logger: self.logger(msg)
        else: print(msg)

    def set_api_key(self, index):
        with self.lock:
            self.current_index = index % len(self.api_keys)
            genai.configure(api_key=self.api_keys[self.current_index])
            self.log(f"🔑 Đang dùng key {self.current_index + 1}/{len(self.api_keys)}")

    def _extract_text_from_gemini_response(self, response):
        """Chuẩn hoá response từ Gemini về str."""
        if response is None: return ""
        if isinstance(response, str): return response
        if hasattr(response, "text"): return response.text
        if isinstance(response, dict) and "text" in response: return response["text"]
        if isinstance(response, list) and len(response) > 0:
            return self._extract_text_from_gemini_response(response[0])
        return str(response)

    def generate(self, prompt, retries=10):
        attempt = 0

        while attempt < retries:
            with self.lock:
                api_key = self.api_keys[self.current_index]
                current_key_num = self.current_index + 1

                # rotate key ngay từ đầu
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
                    time.sleep(10)
                    continue

                # 🔥 lỗi khác
                else:
                    self.log(f"❌ Lỗi API (Key {current_key_num}): {e}")
                    time.sleep(2)
                    continue

        self.log("💀 Hết retry, bỏ request")
        return None
