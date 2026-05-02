import json
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from core.utils import read_docx, extract_number, write_smooth_docx, load_category
import json5
import math
from json_repair import repair_json

class Smooth:
    def __init__(self, gemini, site, book_id, rules, logger=print):
        self.site = site
        self.book_id = book_id
        self.gemini = gemini
        self.log = logger
        self.rules = rules
        self.category = load_category(site, book_id)
        self.lock = threading.Lock()

        self.input_folder = os.path.join("../output/translate", site, str(book_id))
        self.smooth_output_folder = os.path.join("../output/smooth", site, f"{book_id}")
        self.smooth_error_folder = os.path.join("../output/smooth", site, f"{book_id}_error")
        self.smooth_skip_folder = os.path.join("../output/smooth", site, f"{book_id}_skip")

        os.makedirs(self.input_folder, exist_ok=True)
        os.makedirs(self.smooth_output_folder, exist_ok=True)
        os.makedirs(self.smooth_error_folder, exist_ok=True)
        os.makedirs(self.smooth_skip_folder, exist_ok=True)

        self.skip_file = os.path.join(self.smooth_skip_folder, "skip_chapters.json")
        if os.path.exists(self.skip_file):
            with open(self.skip_file, "r", encoding="utf-8") as f:
                self.skip_data = json.load(f)
        else:
            self.skip_data = {"skip": []}

    def save_skip(self):
        with self.lock:
            with open(self.skip_file, "w", encoding="utf-8") as f:
                json.dump(self.skip_data, f, ensure_ascii=False, indent=4)

    def clean_json_text(self, text):
        # Cắt bỏ các tag markdown markdown nếu LLM bướng bỉnh sinh ra
        text = re.sub(r'^```json\s*', '', text, flags=re.MULTILINE)
        text = re.sub(r'^```\s*', '', text, flags=re.MULTILINE)
        try:
            # Tìm block json đầu tiên hợp lệ
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return match.group().strip()
            return text.strip()
        except: 
            return text
    
    def fix_dot_and_quote(self, content: str) -> str:
        # Chỉ xử lý khi không có xuống dòng
        if content.count("\n") >= 20:
            print("deo co loz oi")
            return content

        # 1. Fix ". ." → ".."
        content = content.replace(". .", "..")

        content = content.replace("...", "__ELLIPSIS___") # tạm thay ... để tránh bị split

        # 2. Tách câu theo dấu chấm
        content = content.replace(". ", ".\n")

        # 3. Tách đoạn theo dấu ngoặc kép: "abc" "def"
        content = content.replace('" "', '"\n"')

        content = content.replace('" ', '"\n') # nếu có trường hợp "abc" "def" (dấu cách sau dấu ngoặc kép cuối)

        content = content.replace("__ELLIPSIS___", "...") # khôi phục lại ...

        # 4. Cleanup: tránh nhiều dòng trống
        content = re.sub(r'\n{2,}', '\n\n', content)

        return content.strip()

    def split_text(self, text, max_words=1000):
        paragraphs = [p.strip() for p in text.split('\n') if p.strip()]
        
        # Tổng số từ
        total_words = sum(len(p.split()) for p in paragraphs)

        # Số phần
        num_parts = math.ceil(total_words / max_words)

        # Max words mới (chia đều)
        new_max_words = math.ceil(total_words / num_parts)

        parts = []
        current_part = []
        current_words = 0

        for para in paragraphs:
            wc = len(para.split())

            # 🔥 Nếu đã đủ (num_parts - 1) part → phần còn lại gom hết
            if len(parts) == num_parts - 1:
                current_part.append(para)
                current_words += wc
                continue

            # logic cắt bình thường
            if current_part and current_words + wc > new_max_words:
                parts.append("\n\n".join(current_part))
                current_part = [para]
                current_words = wc
            else:
                current_part.append(para)
                current_words += wc

        if current_part:
            parts.append("\n\n".join(current_part))

        return parts

    def build_prompt(self, chapter_number, text, translate_prev, part_info=""):
        return f"""
        Bạn là một đại thần tác giả văn học mạng và chuyên gia cải biên (rewriter) đẳng cấp. Nhiệm vụ của bạn là "đập đi xây lại" hoàn toàn bản dịch thô, biến tấu nó thành một áng văn mang phong cách hoàn toàn mới, sinh động và cuốn hút hơn gấp nhiều lần, nhưng PHẢI BẢO TOÀN TUYỆT ĐỐI Ý CHÍNH, BỐ CỤC VÀ DUNG LƯỢNG của bản gốc.

        Quy tắc bắt buộc (Lệnh tối cao):

        1. THOÁT LY HOÀN TOÀN CÂU CHỮ NHƯNG GIỮ NGUYÊN CỐT TRUYỆN: Không chỉ là thay từ đồng nghĩa, bạn phải diễn đạt lại toàn bộ đoạn văn bằng một tư duy ngôn ngữ khác biệt, đập bỏ hoàn toàn cấu trúc câu gốc. Sử dụng từ vựng phong phú, linh hoạt, thêm thắt các biện pháp tu từ để câu văn mang đậm chất văn học mạng (không kiểm duyệt). Mọi câu chữ phải được viết mới hoàn toàn. Tuy nhiên, TUYỆT ĐỐI không làm sai lệch cốt truyện, logic, diễn biến, tính cách nhân vật; giữ nguyên xưng hô, ngôi thứ 3 và các danh từ riêng.

        2. ĐẢM BẢO TƯƠNG ĐƯƠNG SỐ CHỮ: Dù thay đổi hoàn toàn cách diễn đạt, bạn không được tóm tắt hay cắt xén chi tiết, hành động hay câu thoại nào. Phải phóng tác đầy đủ từng ý. Dung lượng (tổng số chữ) của bản edit phải tương đương với bản gốc, độ chênh lệch không được vượt quá 10%.

        3. GIỮ NGUYÊN CẤU TRÚC ĐOẠN (TỶ LỆ 1:1): Bản gốc có bao nhiêu đoạn văn (paragraph), bản edit phải có chính xác bấy nhiêu đoạn. Tuyệt đối KHÔNG gộp đoạn hay tách đoạn, dù có biến tấu văn phong bay bổng đến đâu.
        
        4. CHUYỂN ĐỔI ĐỊNH DẠNG LỜI THOẠI: Tất cả các câu thoại đang sử dụng dấu gạch ngang đầu câu (ví dụ: - Lời thoại...) BẮT BUỘC phải chuyển hoàn toàn sang định dạng dùng dấu ngoặc kép (ví dụ: "Lời thoại...").

        5. XỬ LÝ DẤU NGẮT QUÃNG: Tất cả các dấu gạch ngang dài biểu thị sự ngắt quãng, kéo dài giọng hoặc bỏ lửng (ví dụ: ——) BẮT BUỘC phải được chuyển đổi thành dấu ba chấm (...).

        ***LƯU Ý TRÌNH BÀY (RẤT QUAN TRỌNG)***: TUYỆT ĐỐI KHÔNG tự ý ngắt dòng giữa câu. GIỮA CÁC ĐOẠN VĂN BẮT BUỘC PHẢI CÁCH NHAU BẰNG 2 DẤU XUỐNG DÒNG (\\n\\n).
        
        Cấu trúc JSON đầu ra bắt buộc (Chỉ trả về 1 object duy nhất):
        {{
        "chapter_number": "{chapter_number}",
        "chapter_title": "Nếu trong bản gốc có tiêu đề chương, hãy giữ nguyên tiêu đề đó. Nếu không có, hãy để trống, không ghi kiểu Chương 1, Chương 2...",
        "chapter_content": "Toàn bộ chương truyện đã được 'đập đi xây lại' với văn phong hoàn toàn mới.",
        "other_content" : "Toàn bộ nội dung không liên quan đến truyện (quảng cáo, lời tác giả, lời converter, đề cử kim phiếu, p/s...). Nếu không có thì để chuỗi rỗng."
        }}

        Dưới đây là nội dung chương {chapter_number} cần được viết lại hoàn toàn:
        {text}
        """

    def smooth_chapter(self, chapter_number, text, max_words_per_part=1000, stop_event=None):
        text_parts = self.split_text(text, max_words_per_part)
        full_content = []
        final_title = f"Chương {chapter_number}"
        
        files = sorted([f for f in os.listdir(self.input_folder) if extract_number(f)], key=extract_number)
        prev_num = chapter_number - 1
        prev_filename = next((x for x in files if extract_number(x) == prev_num), None) if prev_num > 0 else None
        prev_context = ""
        if prev_filename:
            path = os.path.join(self.input_folder, prev_filename)
            prev_context = f"=== CHƯƠNG TRƯỚC ===\n" + (read_docx(path) if path.endswith(".docx") else open(path, encoding="utf-8").read())

        i = 0
        while i < len(text_parts):
            part_text = text_parts[i]
            num_parts = len(text_parts)
            label = f"(P{i+1}/{num_parts})"
            
            prompt = self.build_prompt(chapter_number, part_text, prev_context if i==0 else f"=== PHẦN TRƯỚC ===\n{text_parts[i-1]}", label)
            
            success, attempt = False, 0
            while not success:
                if stop_event and stop_event.is_set(): return {"error": "stop"}
                attempt += 1
                self.log(f"🌀 Chương {chapter_number} {label}: Thử lần {attempt}...")
                
                try:
                    raw_response = self.gemini.generate(prompt)
                    res_text = raw_response.text
                    if not res_text: raise ValueError("Gemini rỗng")
                    
                    cleaned_text = self.clean_json_text(res_text)

                    res_json = None
                    try:
                        res_json = json.loads(cleaned_text)
                    except json.JSONDecodeError as je:
                        self.log(f"⚠️ JSON lỗi cú pháp. Đang tiến hành tự động vá lỗi (json5/json_repair)...")
                        
                        try:
                            # 2. Nếu lỗi, thử dùng json5 (bạn đã import sẵn)
                            res_json = json5.loads(cleaned_text)
                        except Exception:
                            self.log("💡 Không thể phân tích, retry")
                            raise je # Nếu không có thư viện thì đành chịu, throw lỗi để gen lại

                    
                    if isinstance(res_json, list): res_json = res_json[0]
                    
                    content = res_json.get("chapter_content", "")

                    print(content)

                    content = self.fix_dot_and_quote(content)

                    print(content)                    
                    
                    # -----------------------------------

                    other = res_json.get("other_content", "")
                    if i == 0: final_title = res_json.get("chapter_title", final_title)

                    orig_w = len(part_text.split())
                    smooth_w = len(content.split()) + len(other.split())
                    ratio = smooth_w / max(orig_w, 1)
                    
                    self.log(f"📏 Chương {chapter_number} {label}: Tỉ lệ {ratio:.2f} | Gốc: {orig_w} | Mượt: {smooth_w}")
                    if (orig_w < 1200 and 0.8 <= ratio <= 1.30) or (orig_w >= 1200 and 0.85 <= ratio <= 1.25):
                        full_content.append(content)
                        success = True
                        i += 1
                    else:
                        time.sleep(2)
                except Exception as e:
                    err_msg = str(e)
                    # Xử lý lỗi bị chặn (Blocked content)
                    if "parts" in err_msg and "none were returned" in err_msg:
                        words_count = len(part_text.split())
                        if words_count > 100:
                            self.log(f"⚠️ Chương {chapter_number} {label} bị chặn (Blocked). Tiến hành tách đôi phần này...")
                            # Tách phần hiện tại làm đôi
                            sub_parts = self.split_text(part_text, max_words=words_count // 2 + 1)
                            if len(sub_parts) > 1:
                                # Thay thế phần hiện tại bằng các phần nhỏ hơn
                                text_parts[i:i+1] = sub_parts
                                success = True # Thoát vòng lặp retry để quay lại xử lý text_parts mới
                                continue
                        else:
                            self.log(f"⚠️ Chương {chapter_number} {label} bị chặn nhưng quá ngắn. Bỏ qua làm mượt đoạn này.")
                            full_content.append(part_text) # Giữ nguyên gốc
                            success, i = True, i + 1
                            continue

                    self.log(f"❌ Lỗi chương {chapter_number} {label}: {e}")
                    if attempt > 1000: return {"error": "fatal"}
                    time.sleep(2)

        out_path = os.path.join(self.smooth_output_folder, f"Chuong_{chapter_number:05d}.docx")
        write_smooth_docx(out_path, chapter_number, final_title, "\n\n".join(full_content))
        self.log(f"✔ Đã lưu chương {chapter_number}")
        return None

    def process_file(self, f, stop_event, max_words):
        if stop_event and stop_event.is_set(): return "stop"
        chapter_number = extract_number(f)
        if not chapter_number or chapter_number in self.skip_data.get("skip", []): return None
        if os.path.exists(os.path.join(self.smooth_output_folder, f"Chuong_{chapter_number:05d}.docx")): return None

        path = os.path.join(self.input_folder, f)
        text = read_docx(path) if f.endswith(".docx") else open(path, encoding="utf-8").read()
        if not text.strip() or len(text.split()) <= 100: return None
        
        res = self.smooth_chapter(chapter_number, text, max_words, stop_event)
        return "stop" if res and res.get("error") in ["fatal", "stop"] else None

    def smooth_range(self, start=None, end=None, stop_event=None, num_workers=1, max_words_per_part=1000):
        files = sorted([f for f in os.listdir(self.input_folder) if extract_number(f)], key=extract_number)
        filtered = [f for f in files if (not start or extract_number(f) >= start) and (not end or extract_number(f) <= end)]
        
        self.log(f"🚀 Xử lý {len(filtered)} file, {num_workers} workers.")
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(self.process_file, f, stop_event, max_words_per_part) for f in filtered]
            for future in futures:
                if future.result() == "stop":
                    stop_event.set()
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
