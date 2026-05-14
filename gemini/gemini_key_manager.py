import os
import time
import threading
import google.generativeai as genai
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import json5
import json
import re

CONFIG_DIR = "configs"
KEYS_CONFIG_PATH = os.path.join(CONFIG_DIR, "keys.json")
HEALTH_CONFIG_PATH = os.path.join(CONFIG_DIR, "key_health.json")

def load_key_health():
    if os.path.exists(HEALTH_CONFIG_PATH):
        try:
            with open(HEALTH_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}

def save_key_health(health_data):
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(HEALTH_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(health_data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"❌ Lỗi lưu sức khỏe Key: {e}")

def load_api_keys():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)

    data = []
    if os.path.exists(KEYS_CONFIG_PATH):
        try:
            with open(KEYS_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            pass

    # Nếu data là list string (định dạng cũ), migrate sang định dạng mới
    if data and isinstance(data, list) and isinstance(data[0], str):
        data = [{"gmail": "Default", "keys": data}]
        save_api_keys(data)
    
    # Nếu chưa có JSON, thử đọc từ .env hoặc keys.txt
    if not data:
        from dotenv import load_dotenv
        load_dotenv()
        api_keys = []
        env_keys = os.getenv("API_KEYS")
        if env_keys:
            api_keys = [k.strip() for k in env_keys.split(",") if k.strip()]
        elif os.path.exists("keys.txt"):
            with open("keys.txt", "r", encoding="utf-8") as f:
                api_keys = [line.strip() for line in f if line.strip()]
        
        if api_keys:
            data = [{"gmail": "Default", "keys": api_keys}]
            save_api_keys(data)
            
    return data

def save_api_keys(accounts_data):
    """Lưu dữ liệu theo cấu trúc: [{"gmail": "...", "keys": [...]}, ...]"""
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(KEYS_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(accounts_data, f, ensure_ascii=False, indent=4)

class GeminiKeyManager:
    # Biến Class để chia sẻ trạng thái giữa các instance
    GLOBAL_KEY_HEALTH = load_key_health()
    HEALTH_LOCK = threading.Lock()

    def __init__(self, model_name = None, logger=print, rpm_limit=8):
        self.accounts = load_api_keys() 
        self.model_name = model_name or "gemini-2.0-flash-lite-preview-02-05"
        self.logger = logger
        self.lock = threading.Lock()
        
        self.current_acc_idx = 0
        self.current_key_idx = 0 
        
        # --- Cấu hình Rate Limiting ---
        self.rpm_limit = rpm_limit
        self.request_timestamps = [] 
        self.last_request_start = 0  
        self.request_spacing = 3     

    def log(self, msg):
        if self.logger: self.logger(msg)
        else: print(msg)

    def _wait_for_rate_limit(self):
        """Hàm điều phối luồng: Chờ nếu vi phạm RPM hoặc giãn cách giây"""
        while True:
            with self.lock:
                now = time.time()
                self.request_timestamps = [t for t in self.request_timestamps if now - t < 60]
                
                if len(self.request_timestamps) >= self.rpm_limit:
                    wait_time = 60 - (now - self.request_timestamps[0])
                    if wait_time > 0:
                        self.log(f"⏳ Đạt ngưỡng {self.rpm_limit} RPM. Nghỉ {wait_time:.1f}s...")
                        time.sleep(wait_time)
                        continue 
                
                time_since_last = now - self.last_request_start
                if time_since_last < self.request_spacing:
                    wait_gap = self.request_spacing - time_since_last
                    time.sleep(wait_gap)
                    continue
                
                self.last_request_start = time.time()
                self.request_timestamps.append(self.last_request_start)
                break

    def _get_key_health(self, api_key):
        """Lấy thông tin sức khỏe của Key, có cơ chế reset theo ngày và vá lỗi thiếu field"""
        now = time.time()
        today = time.strftime("%Y-%m-%d")
        
        with self.HEALTH_LOCK:
            if api_key not in self.GLOBAL_KEY_HEALTH:
                self.GLOBAL_KEY_HEALTH[api_key] = {}
            
            health = self.GLOBAL_KEY_HEALTH[api_key]
            
            # Đảm bảo các field bắt buộc luôn tồn tại (Vá lỗi cho data cũ)
            defaults = {
                "daily_errors": 0, 
                "total_errors": 0,
                "cooldown_until": 0, 
                "dead_until": 0, 
                "last_date": today,
                "status": "Healthy"
            }
            for key, val in defaults.items():
                if key not in health:
                    health[key] = val
            
            # Nếu sang ngày mới, reset bộ đếm lỗi ngày
            if health.get("last_date") != today:
                health["daily_errors"] = 0
                health["dead_until"] = 0
                health["last_date"] = today
                health["status"] = "Healthy"
                
            return health

    def _get_next_key(self):
        """Lấy key khả dụng tiếp theo trong Gmail hiện tại."""
        now = time.time()
        
        with self.lock:
            acc_idx = self.current_acc_idx
            acc = self.accounts[acc_idx]
            keys = acc.get("keys", [])
            gmail = acc.get("gmail", "Unknown")
            
            if not keys: return None, gmail, acc_idx, 0

            # Thử tìm một key "khỏe mạnh"
            for i in range(len(keys)):
                k_idx = (self.current_key_idx + i) % len(keys)
                key_str = keys[k_idx]
                health = self._get_key_health(key_str)
                
                if now < health["dead_until"]: continue
                if now < health["cooldown_until"]: continue
                
                self.current_key_idx = (k_idx + 1) % len(keys)
                return key_str, gmail, acc_idx, k_idx + 1
            
            return None, gmail, acc_idx, 0

    def _mark_key_error(self, api_key, gmail, error_msg=""):
        """Phân loại lỗi và xử lý Cooldown/Khóa"""
        now = time.time()
        err_str = str(error_msg).lower()
        short_err = str(error_msg)[:60]
        
        with self.HEALTH_LOCK:
            health = self.GLOBAL_KEY_HEALTH[api_key]
            health["total_errors"] += 1
            
            # 1. Phân loại lỗi 429 Resource Exhausted (NẶNG)
            if "429" in err_str and ("exhausted" in err_str or "resource" in err_str):
                health["dead_until"] = now + (5 * 3600)
                health["status"] = "Resource Exhausted"
                self.log(f"💀 [NẶNG] Key {api_key[:8]}... cạn kiệt tài nguyên. KHÓA HẾT NGÀY.")
            
            # 2. Lỗi 429 Quota Exceeded (THƯỜNG)
            elif "429" in err_str or "limit" in err_str:
                health["daily_errors"] += 1
                if health["daily_errors"] >= 2:
                    health["dead_until"] = now + (5 * 3600)
                    health["status"] = "Quota Limit"
                    self.log(f"💀 Key {api_key[:8]}... hết hạn mức (2/2). KHÓA HẾT NGÀY.")
                else:
                    health["cooldown_until"] = now + 60
                    health["status"] = "Cooldown (429)"
                    self.log(f"⚠️ Key {api_key[:8]}... lỗi hạn mức ({health['daily_errors']}/2). Nghỉ 60s.")
            
            # 3. Lỗi hệ thống khác (503, 500, network...)
            else:
                health["cooldown_until"] = now + 60
                health["status"] = f"Error: {short_err}"
                self.log(f"⚠️ Key {api_key[:8]}... lỗi: {short_err}. Nghỉ 60s.")
            
            save_key_health(self.GLOBAL_KEY_HEALTH)

    def generate(self, prompt, retries=3):
        attempt = 0
        while attempt < retries:
            self._wait_for_rate_limit()

            # 1. Thử lấy key từ Gmail hiện tại
            api_key, gmail_name, acc_idx, key_num = self._get_next_key()
            
            # 2. Nếu Gmail hiện tại "tèo" sạch key khả dụng
            if api_key is None:
                if len(self.accounts) > 1:
                    self.log(f"🔄 Gmail {gmail_name} hết key khả dụng. Đang đổi Gmail...")
                    with self.lock:
                        self.current_acc_idx = (self.current_acc_idx + 1) % len(self.accounts)
                        self.current_key_idx = 0
                    attempt += 1
                    # Nghỉ cứng 60s khi đổi bộ Gmail
                    time.sleep(30)
                    continue
                else:
                    self.log(f"😴 Toàn bộ dàn Key đang bận/lỗi. Nghỉ 60s chờ hồi phục...")
                    time.sleep(600)
                    attempt += 1
                    continue

            try:
                attempt_start = time.perf_counter()
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel(self.model_name)

                self.log(f"🚀 [Gmail: {gmail_name}] Key {key_num} | Call API...")

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
                self.log(f"⏱ [Key {key_num}] Success | Time: {attempt_end - attempt_start:.2f}s")
                return response

            except Exception as e:
                err = str(e)
                attempt += 1
                
                # Gọi hàm mark_error để phân loại và nghỉ 60s
                self._mark_key_error(api_key, gmail_name, error_msg=err)
                
                # Nghỉ cứng sau khi gặp bất kỳ lỗi nào
                time.sleep(60)
                continue

        self.log("💀 Hết retry, bỏ request")
        return None
