import customtkinter as ctk
import os, threading
from smooth.smooth import Smooth
from gemini.gemini_key_manager import GeminiKeyManager
from core.utils import load_sites, load_rules, move_book_folders, OUTPUT_PATH, DONE_PATH, merge_docx_to_txt
from core.gemini_config import load_gemini_models, load_default_model


TRANSLATE_PATH = os.path.join(OUTPUT_PATH, "translate")
DONE_TRANSLATE_PATH = os.path.join(DONE_PATH, "translate")
SMOOTH_PATH = os.path.join(OUTPUT_PATH, "smooth")
DONE_SMOOTH_PATH = os.path.join(DONE_PATH, "smooth")
MERGE_PATH = os.path.join(OUTPUT_PATH, "merge")

class SmoothToolApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("📘 Làm mượt")
        self.geometry("1100x750")
        self.stop_event = threading.Event()
        self.view_mode = "Đang làm" # Hoặc "Đã xong"

        # Layout chia 3 cột
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)
        self.grid_columnconfigure(2, weight=2)
        self.grid_rowconfigure(0, weight=1)

        self.create_left_panel()
        self.create_middle_panel()
        self.create_right_panel()
        self.refresh_book_list()

    # ================================
    # 🌐 Panel trái — chọn website
    # ================================
    def create_left_panel(self):
        self.left = ctk.CTkFrame(self)
        self.left.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(self.left, text="🌐 Website", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=(10,5))
        self.sites_config = load_sites()
        site_list = list(self.sites_config.keys()) or ["unknown"]

        self.site_var = ctk.StringVar(value=site_list[0])

        self.site_menu = ctk.CTkOptionMenu(
            self.left,
            values=site_list,
            variable=self.site_var,
            command=self.refresh_book_list
        )
        self.site_menu.pack(pady=(0, 10))

        ctk.CTkButton(
            self.left,
            text="Làm mới",
            width=120,
            command=lambda: self.refresh_book_list()
        ).pack(padx=5)

    # ================================
    # 📚 Panel giữa — danh sách truyện
    # ================================
    def create_middle_panel(self):
        self.middle = ctk.CTkFrame(self)
        self.middle.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(self.middle, text="📚 Danh sách truyện", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        
        # Thanh chuyển đổi chế độ xem
        self.mode_switch = ctk.CTkSegmentedButton(
            self.middle, 
            values=["Đang làm", "Đã xong"],
            command=self.change_view_mode
        )
        self.mode_switch.set("Đang làm")
        self.mode_switch.pack(pady=(0, 10))

        # Thanh tìm kiếm
        search_frame = ctk.CTkFrame(self.middle, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", self.on_search_change)
        
        self.search_entry = ctk.CTkEntry(
            search_frame, 
            placeholder_text="🔍 Tìm kiếm tên truyện...",
            textvariable=self.search_var
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        ctk.CTkButton(search_frame, text="X", width=30, command=lambda: self.search_var.set("")).pack(side="right")

        self.book_list = ctk.CTkScrollableFrame(self.middle)
        self.book_list.pack(expand=True, fill="both", padx=10, pady=10)
        
        self.all_folders = [] # Cache danh sách folder

    def change_view_mode(self, mode):
        self.view_mode = mode
        self.refresh_book_list()

    def on_search_change(self, *args):
        # Debounce: Chờ 300ms sau khi ngừng gõ mới thực hiện lọc để tránh lag
        if hasattr(self, "_search_timer"):
            self.after_cancel(self._search_timer)
        self._search_timer = self.after(300, self.filter_books)

    def filter_books(self):
        query = self.search_var.get().lower()
        filtered = [f for f in self.all_folders if query in f.lower()]
        self.render_book_list(filtered)

    def refresh_book_list(self, *_):
        # Quyết định đường dẫn dựa trên chế độ xem
        path_base = TRANSLATE_PATH if self.view_mode == "Đang làm" else DONE_TRANSLATE_PATH
        BASE_PATH = os.path.join(path_base, self.site_var.get())
        
        # Reset tìm kiếm khi đổi site hoặc làm mới
        self.search_var.set("")
        
        INVALID_SUFFIX = ("_error", "_skip", "_error", "_summary", "_knowlegde")

        if not os.path.exists(BASE_PATH):
            os.makedirs(BASE_PATH, exist_ok=True)

        # Cập nhật cache danh sách folder từ ổ đĩa
        self.all_folders = []
        try:
            for folder in sorted(os.listdir(BASE_PATH)):
                full_path = os.path.join(BASE_PATH, folder)
                if os.path.isdir(full_path) and not folder.endswith(INVALID_SUFFIX):
                    self.all_folders.append(folder)
        except Exception as e:
            self.log(f"❌ Lỗi đọc danh sách truyện: {e}")

        self.filter_books()

    def toggle_book_status(self, book_id):
        to_done = (self.view_mode == "Đang làm")
        site = self.site_var.get()
        
        success = move_book_folders(site, book_id, to_done)
        if success:
            action = "hoàn thành" if to_done else "khôi phục"
            self.log(f"✅ Đã {action} truyện: {book_id}")
            self.refresh_book_list()
        else:
            self.log(f"❌ Không thể di chuyển folder cho truyện: {book_id}")

    def render_book_list(self, folders):
        # Xóa các widget cũ trong danh sách
        for w in self.book_list.winfo_children():
            w.destroy()

        if not folders:
            msg = "Chưa có truyện nào đã xong" if self.view_mode == "Đã xong" else "Không tìm thấy truyện nào"
            ctk.CTkLabel(self.book_list, text=msg).pack(pady=20)
            return

        for folder in folders:
            frame = ctk.CTkFrame(self.book_list)
            frame.pack(fill="x", pady=3, padx=5)
            
            # Layout Grid: Cột 0 co giãn, Cột 1-3 cố định cho nút
            frame.grid_columnconfigure(0, weight=1)
            frame.grid_columnconfigure(1, weight=0)
            frame.grid_columnconfigure(2, weight=0)
            frame.grid_columnconfigure(3, weight=0)

            label = ctk.CTkLabel(
                frame, 
                text=folder, 
                anchor="w", 
                justify="left",
                font=ctk.CTkFont(size=14, weight="bold"),
                wraplength=350
            )
            label.grid(row=0, column=0, sticky="ew", padx=(10, 5), pady=8)

            if self.view_mode == "Đang làm":
                # Nút Làm mượt
                btn_smooth = ctk.CTkButton(
                    frame, 
                    text="Làm mượt", 
                    width=90,
                    command=lambda f=folder: self.choose_options_popup(f)
                )
                btn_smooth.grid(row=0, column=1, padx=5, pady=8, sticky="e")

                # Nút Gộp
                btn_merge = ctk.CTkButton(
                    frame, 
                    text="Gộp", 
                    width=60,
                    fg_color="#6c757d",
                    hover_color="#5a6268",
                    command=lambda f=folder: self.choose_merge_options_popup(f)
                )
                btn_merge.grid(row=0, column=2, padx=5, pady=8, sticky="e")

                # Nút Xong
                btn_done = ctk.CTkButton(
                    frame, 
                    text="Xong", 
                    width=60,
                    fg_color="#28a745", 
                    hover_color="#218838",
                    command=lambda f=folder: self.toggle_book_status(f)
                )
                btn_done.grid(row=0, column=3, padx=(5, 10), pady=8, sticky="e")
            else:
                # Chế độ "Đã xong" - Nút Khôi phục
                btn_restore = ctk.CTkButton(
                    frame, 
                    text="Khôi phục", 
                    width=120,
                    fg_color="#17a2b8",
                    hover_color="#138496",
                    command=lambda f=folder: self.toggle_book_status(f)
                )
                btn_restore.grid(row=0, column=1, columnspan=3, padx=10, pady=8, sticky="e")

    def choose_merge_options_popup(self, book_id):
        popup = ctk.CTkToplevel(self)
        popup.title(f"Gộp file: {book_id}")
        popup.geometry("300x200")
        popup.grab_set()

        ctk.CTkLabel(popup, text="Phạm vi chương cần gộp:", font=ctk.CTkFont(size=14, weight="bold")).pack(pady=10)

        f_range = ctk.CTkFrame(popup, fg_color="transparent")
        f_range.pack(pady=5)

        ctk.CTkLabel(f_range, text="Từ:").grid(row=0, column=0, padx=5)
        start_var = ctk.StringVar(value="1")
        ctk.CTkEntry(f_range, textvariable=start_var, width=60).grid(row=0, column=1, padx=5)

        ctk.CTkLabel(f_range, text="Đến:").grid(row=0, column=2, padx=5)
        end_var = ctk.StringVar(value="100")
        ctk.CTkEntry(f_range, textvariable=end_var, width=60).grid(row=0, column=3, padx=5)

        ctk.CTkButton(
            popup, 
            text="Bắt đầu gộp", 
            command=lambda: self.execute_merge(popup, book_id, start_var.get(), end_var.get())
        ).pack(pady=20)

    def execute_merge(self, popup, book_id, start_str, end_str):
        try:
            start = int(start_str)
            end = int(end_str)
        except:
            self.log("❌ Lỗi: Start/End phải là số!")
            return

        popup.destroy()
        
        # Chạy gộp trong thread riêng để không treo GUI
        threading.Thread(target=self._execute_merge_thread, args=(book_id, start, end), daemon=True).start()

    def _execute_merge_thread(self, book_id, start, end):
        # Quyết định đường dẫn nguồn dựa trên chế độ xem
        path_base = SMOOTH_PATH if self.view_mode == "Đang làm" else DONE_SMOOTH_PATH
        input_folder = os.path.join(path_base, self.site_var.get(), book_id)
        
        # Đường dẫn đích
        os.makedirs(MERGE_PATH, exist_ok=True)
        output_filename = f"{book_id} {start} - {end}.txt"
        output_file = os.path.join(MERGE_PATH, output_filename)

        self.log(f"⏳ Đang gộp {book_id} (Chương {start} - {end})...")
        
        try:
            success, result = merge_docx_to_txt(input_folder, start, end, output_file)
            if success:
                self.log(f"✅ Gộp thành công! File lưu tại: {result}")
            else:
                self.log(f"❌ Gộp thất bại: {result}")
        except Exception as e:
            self.log(f"❌ Lỗi hệ thống khi gộp: {e}")

    # =================================
    # 🧠 Panel phải — log + dừng
    # =================================
    def create_right_panel(self):
        self.right = ctk.CTkFrame(self)
        self.right.grid(row=0, column=2, sticky="nsew", padx=10, pady=10)

        ctk.CTkLabel(self.right, text="🤖 Gemini Model", font=ctk.CTkFont(size=16, weight="bold")).pack(pady=5)

        models = load_gemini_models()
        default = load_default_model() or models[0]
        self.model_var = ctk.StringVar(value=default)

        ctk.CTkOptionMenu(
            self.right,
            values=models,
            variable=self.model_var
        ).pack(pady=5)

        # --- Log Gemini ---
        ctk.CTkLabel(self.right, text="🧠 Log key", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        self.gemini_box = ctk.CTkTextbox(self.right, wrap="word", state="disabled")
        self.gemini_box.pack(expand=True, fill="both", padx=10, pady=10)

        ctk.CTkLabel(self.right, text="🧠 Log làm mượt", font=ctk.CTkFont(size=18, weight="bold")).pack(pady=10)
        self.log_box = ctk.CTkTextbox(self.right, wrap="word", state="disabled")
        self.log_box.pack(expand=True, fill="both", padx=10, pady=10)

        ctk.CTkButton(self.right, text="🛑 Dừng", fg_color="red", command=self.stop_smooth).pack(pady=5)

    def log_gemini(self, msg):
        # thread-safe log
        self.after(0, self._append_log_gemini, msg)

    def _append_log_gemini(self, msg):
        self.gemini_box.configure(state="normal")
        self.gemini_box.insert("end", msg + "\n")
        self.gemini_box.see("end")
        self.gemini_box.configure(state="disabled")

    def log(self, msg):
        # thread-safe log
        self.after(0, self._append_log, msg)

    def _append_log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def stop_smooth(self):
        self.stop_event.set()
        self.log("🛑 Đã gửi yêu cầu dừng...")

    # ================================
    # 🧩 Logic học toàn bộ truyện
    # ================================
    def smooth_all(self, book_id, rules, num_workers=1, max_words_per_part=1000):
        threading.Thread(target=self._smooth_all, args=(book_id, rules, num_workers, max_words_per_part), daemon=True).start()

    def _smooth_all(self, book_id, rules, num_workers=1, max_words_per_part=1000):
        gemini = GeminiKeyManager(self.model_var.get(), self.log_gemini)
        smooth = Smooth(gemini=gemini, site=self.site_var.get(), book_id=book_id, rules=rules, logger=self.log)

        self.log(f"📘 Bắt đầu dịch truyện: {book_id} với {num_workers} worker(s), {max_words_per_part} chữ/phần")
        self.stop_event.clear()

        smooth.smooth_range(start=None, end=None, stop_event=self.stop_event, num_workers=num_workers, max_words_per_part=max_words_per_part)
        
        self.log(f"🎯 Hoàn tất toàn bộ truyện: {book_id}")

    def choose_options_popup(self, book_id):
        
        rules = load_rules()

        if not rules:
            self.log("⚠ Không tìm thấy rule nào trong thư mục /rules")
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Chọn quy tắc dịch")
        popup.geometry("350x280")
        popup.grab_set() 

        ctk.CTkLabel(
            popup,
            text="Chọn quy tắc dịch:",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)

        rule_var = ctk.StringVar(value=list(rules.keys())[0])

        style_menu = ctk.CTkOptionMenu(
            popup,
            values=list(rules.keys()),
            variable=rule_var
        )
        style_menu.pack(pady=5)

        ctk.CTkLabel(
            popup,
            text="Số lượng worker:",
            font=ctk.CTkFont(size=14)
        ).pack(pady=(10, 0))

        worker_var = ctk.StringVar(value="1")
        worker_entry = ctk.CTkEntry(popup, textvariable=worker_var, width=100)
        worker_entry.pack(pady=5)

        ctk.CTkLabel(
            popup,
            text="Số chữ tối đa/phần:",
            font=ctk.CTkFont(size=14)
        ).pack(pady=(5, 0))

        max_words_var = ctk.StringVar(value="1000")
        max_words_entry = ctk.CTkEntry(popup, textvariable=max_words_var, width=100)
        max_words_entry.pack(pady=5)

        ctk.CTkButton(
            popup,
            text="Bắt đầu",
            command=lambda: self.confirm_options(popup, book_id, rule_var.get(), rules, worker_var.get(), max_words_var.get())
        ).pack(pady=10)

    def confirm_options(self, popup, book_id, rule_name, rules, num_workers, max_words_per_part):
        popup.destroy()
        
        try:
            workers = int(num_workers)
            if workers < 1: workers = 1
        except:
            workers = 1

        try:
            max_words = int(max_words_per_part)
            if max_words < 500: max_words = 500
        except:
            max_words = 1000

        selected_rule = rules.get(rule_name, "")

        self.smooth_all(book_id=book_id, rules=selected_rule, num_workers=workers, max_words_per_part=max_words)
