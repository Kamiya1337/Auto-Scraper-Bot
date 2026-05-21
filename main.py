import time
import os
from dotenv import load_dotenv  # <-- THÊM DÒNG NÀY
load_dotenv()
try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass
import queue
import re
import tkinter as tk
import threading
import sys
import requests
import random
import pyperclip
import hashlib
import urllib.request
import subprocess
import json
import getpass
import google.generativeai as genai
from datetime import datetime
import traceback
import pandas as pd
from openpyxl.styles import Font, Alignment
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains # Thư viện giả lập bàn phím vật lý
from selenium.common.exceptions import TimeoutException, NoSuchElementException

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

class PropertyAutomationEngine:
    def __init__(self, base_url):
        self.base_url = base_url
        self.data = []
        
        self.num_rooms_to_scrape = 1
        self.tu_khoa = ""
        self.sap_xep = ""
        self.quan_huyen = ""
        self.nguon_hang = ""
        
        self.loai_nha = ""
        self.gia_tu = ""
        self.gia_den = ""
        self.tien_ich_list = []
        
        self.tai_anh = False

        self.dang_zalo = False
        self.ten_nhom_zalo = ""
        self.zalo_delay_mode = "real"
        
        self.bo_qua_phong_cu = False
        self.lich_su_file = "lich_su_da_dang.txt"
        self.danh_sach_da_dang = set()
        self.lich_su_anh_file = "lich_su_tai_anh.txt"
        self.danh_sach_da_tai_anh = set()
        if os.path.exists(self.lich_su_anh_file):
            with open(self.lich_su_anh_file, 'r', encoding='utf-8') as f:
                self.danh_sach_da_tai_anh = set([line.strip() for line in f if line.strip()])

        self.blacklist_file = "blacklist.txt"
        self.blacklist_phong = set()
        if os.path.exists(self.blacklist_file):
            with open(self.blacklist_file, 'r', encoding='utf-8') as f:
                self.blacklist_phong = set([line.strip() for line in f if line.strip()])
        else:
            with open(self.blacklist_file, 'w', encoding='utf-8') as f:
                f.write("# Dán link các phòng bạn muốn Robot BỎ QUA vào đây (mỗi link 1 dòng):\n")

        self.tong_thoi_gian_bat_dau = time.time()
        self.thong_ke = {
            'phong_cao': 0,
            'zalo': 0,
            'fb': 0,
            'qr': 0,
            'hunter': 0
        }

        self._tabs = {
            'fb_group':  None,   # Tab đăng bài group — KHÔNG BAO GIỜ ĐÓNG
            'fb_hunt':   None,   # Tab lướt newsfeed săn khách — đóng sau mỗi hunt
            'example':   None,   # Tab example — giữ xuyên suốt session
        }

        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.app_version = "1.0.0"
        self.base_url = os.getenv('FIREBASE_URL')
        self.my_hwid = self.get_machine_hwid() # Lưu HWID để dùng chung

    def day_log_firebase(self, status="Active", error_msg="None"):
        """Hàm đẩy log tĩnh lặng lên Firebase"""
        if not getattr(self, 'base_url', None) or not getattr(self, 'my_hwid', None):
            return
            
        try:
            thoi_gian_chay = int(time.time() - getattr(self, 'tong_thoi_gian_bat_dau', time.time()))
            gio, du = divmod(thoi_gian_chay, 3600)
            phut, giay = divmod(du, 60)
            tong_thoi_gian_treo_may = f"{gio} giờ {phut} phút {giay} giây"
            
            thoi_gian_bat_dau_str = datetime.fromtimestamp(self.tong_thoi_gian_bat_dau).strftime("%Y-%m-%d %H:%M:%S")
            thoi_gian_cap_nhat_cuoi = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            log_data = {
                "app_version": getattr(self, 'app_version', '1.0.0'),
                "status": status,
                "thoi_gian_bat_dau": thoi_gian_bat_dau_str,
                "thoi_gian_cap_nhat_cuoi": thoi_gian_cap_nhat_cuoi,
                "tong_thoi_gian_treo_may": tong_thoi_gian_treo_may,
                "thong_ke_van_hanh": getattr(self, 'thong_ke', {}),
                "lich_su_loi": error_msg
            }
            
            # rstrip('/') để phòng trường hợp link env của bạn có dư dấu gạch chéo
            url = f"{self.base_url.rstrip('/')}/usage_logs/{self.my_hwid}/{self.session_id}.json"
            requests.put(url, json=log_data, timeout=5)
        except:
            pass # Lỗi mạng thì bỏ qua, tuyệt đối không làm sập tool

    def _heartbeat_loop(self):
        """Luồng ngầm (Daemon) đập nhịp tim mỗi 60 giây"""
        while True:
            time.sleep(60)
            self.day_log_firebase(status="Active")

    def tru_token_firebase(self, amount, ly_do=""):
        """Hàm trừ tiền tự động trên Firebase và RAM"""
        if not getattr(self, 'base_url', None) or not getattr(self, 'my_hwid', None): return
        if not hasattr(self, 'current_credits'): return

        if 'token_da_dung' not in self.thong_ke: 
            self.thong_ke['token_da_dung'] = 0
        self.thong_ke['token_da_dung'] += amount
        
        self.current_credits -= amount
        print(f"   💸 [HỆ THỐNG] Đã trừ {amount} Token ({ly_do}). Số dư còn: {self.current_credits:,}")
        
        try:
            url = f"{self.base_url.rstrip('/')}/licenses/{self.my_hwid}.json"
            # Lệnh patch giúp chỉ cập nhật đúng trường "credits" mà không đè mất chữ "status"
            requests.patch(url, json={"credits": self.current_credits}, timeout=5)
        except:
            pass # Lỗi mạng thì vẫn trừ trên RAM để chặn chạy lố trong phiên hiện tại

    def _get_tab(self, name):
        """Trả về handle hợp lệ hoặc None nếu tab đã chết."""
        handle = self._tabs.get(name)
        if handle and handle in self.driver.window_handles:
            return handle
        self._tabs[name] = None
        return None

    def _close_stray_tabs(self):
        """Đóng toàn bộ tab rác — chỉ giữ 3 tab đã đăng ký."""
        registered = set(h for h in self._tabs.values() if h)
        for handle in list(self.driver.window_handles):
            if handle not in registered:
                try:
                    self.driver.switch_to.window(handle)
                    self.driver.close()
                except: pass
        # Switch về tab an toàn nhất
        safe = self._get_tab('fb_group') or self._get_tab('fb_hunt')
        if safe:
            self.driver.switch_to.window(safe)

    def _ensure_tab(self, name, url):
        """Đảm bảo tab tồn tại. Tạo mới nếu đã chết."""
        handle = self._get_tab(name)
        if handle:
            return handle
        # Tạo tab mới
        self.driver.switch_to.new_window('tab')
        handle = self.driver.current_window_handle
        self._tabs[name] = handle
        try:
            self.driver.get(url)
            time.sleep(3)
        except: pass
        return handle

    def force_exit(self, app):
        print("\n👋 Đang đóng hệ thống và giải phóng tài nguyên...")
        self.day_log_firebase(status="Completed")
        try:
            # Đóng driver Selenium nếu đang mở
            if hasattr(self, 'driver'):
                self.driver.quit()
        except:
            pass
        # Dừng toàn bộ chương trình
        app.quit()
        os._exit(0) # Thoát triệt để, kể cả các thread đang chạy ngầm
    
    def get_user_inputs(self):
        try:
            import customtkinter as ctk
            import tkinter.messagebox as mb
        except ImportError:
            print("⚠️ Chưa cài thư viện Giao diện. Vui lòng mở Terminal gõ: pip install customtkinter")
            sys.exit()

        self.check_hwid_security()
        
        ctk.set_appearance_mode("Dark")
        BG_COLOR = "#12121A"       
        CARD_COLOR = "#1C1C28"     
        ACCENT_COLOR = "#6C5CE7"   
        ACCENT_HOVER = "#8572FF"   
        TEXT_COLOR = "#FFFFFF"     
        SUB_TEXT = "#A0A0B0"       

        app = ctk.CTk(fg_color=BG_COLOR)
        app.title("🚀 HANOI STAY PRO MAX - BẢNG ĐIỀU KHIỂN TỔNG")
        app.geometry("1020x820") # Kích thước rộng hơn để chứa 2 cột

        app.protocol("WM_DELETE_WINDOW", lambda: self.force_exit(app))

        # 🍎 CẤU HÌNH FONT APPLE
        APPLE_FONT = "Helvetica" 
        MAIN_FONT = ctk.CTkFont(family=APPLE_FONT, size=13)
        H2_FONT = ctk.CTkFont(family=APPLE_FONT, size=15, weight="bold")
        TITLE_FONT = ctk.CTkFont(family=APPLE_FONT, size=13, weight="bold")

        ctk.CTkLabel(app, text="⚠️ CẢNH BÁO: Khi Robot đang chạy, TUYỆT ĐỐI KHÔNG can thiệp vào trình duyệt!", 
                     text_color="#ED6A5E", font=TITLE_FONT).pack(pady=(10, 5))

        card_acc = ctk.CTkFrame(app, fg_color=CARD_COLOR, corner_radius=15)
        card_acc.pack(fill="x", padx=20, pady=5, ipadx=10, ipady=10)
        
        ctk.CTkLabel(card_acc, text="👤 THÔNG TIN TÀI KHOẢN TRANG WEB", font=H2_FONT, text_color=ACCENT_COLOR).pack(anchor="w", padx=10, pady=(0, 5))
        
        row_acc = ctk.CTkFrame(card_acc, fg_color="transparent")
        row_acc.pack(fill="x", padx=10)
        
        ent_email = ctk.CTkEntry(row_acc, width=280, placeholder_text="Email...", fg_color="#2A2A38", border_color="#3A3A4D", font=MAIN_FONT)
        ent_email.pack(side="left", padx=(0, 15))
        ent_pass = ctk.CTkEntry(row_acc, width=280, placeholder_text="Mật khẩu...", show="•", fg_color="#2A2A38", border_color="#3A3A4D", font=MAIN_FONT)
        ent_pass.pack(side="left", padx=(0, 15))
        ent_phone = ctk.CTkEntry(row_acc, width=280, placeholder_text="SĐT Quảng cáo...", fg_color="#2A2A38", border_color="#3A3A4D", font=MAIN_FONT)
        ent_phone.pack(side="left")

        my_hwid = self.get_machine_hwid()
        if my_hwid == "959DFF6043DBFA00DD04":
            ctk.CTkLabel(card_acc, text="🛠️ [DEV MODE] Chào mừng Tác giả! Đã nạp tài khoản tự động.", text_color="#00CECE", font=ctk.CTkFont(family=APPLE_FONT, size=12)).pack(anchor="w", padx=10, pady=(5,0))
            ent_email.insert(0, os.getenv('EMAIL'))
            ent_pass.insert(0, os.getenv('PASSWORD'))
            ent_phone.insert(0, os.getenv('USER_PHONE'))

        col_container = ctk.CTkFrame(app, fg_color="transparent")
        col_container.pack(fill="both", expand=True, padx=20, pady=5)
        
        col_left = ctk.CTkFrame(col_container, fg_color="transparent")
        col_left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        col_right = ctk.CTkFrame(col_container, fg_color="transparent")
        col_right.pack(side="right", fill="both", expand=True, padx=(10, 0))

        card_data = ctk.CTkFrame(col_left, fg_color=CARD_COLOR, corner_radius=15)
        card_data.pack(fill="both", expand=True, ipadx=10, ipady=10)
        ctk.CTkLabel(card_data, text="🕷️ CÀO DATA & BỘ LỌC", font=H2_FONT, text_color=ACCENT_COLOR).pack(anchor="w", padx=10, pady=(0, 10))
        
        row1 = ctk.CTkFrame(card_data, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(row1, text="Số phòng (0=Chỉ Săn):", font=MAIN_FONT).pack(side="left")
        ent_num_rooms = ctk.CTkEntry(row1, width=80, font=MAIN_FONT)
        ent_num_rooms.insert(0, "1")
        ent_num_rooms.pack(side="left", padx=10)
        sw_bo_qua = ctk.CTkSwitch(row1, text="Bỏ qua phòng cũ (Nam Tào)", progress_color=ACCENT_COLOR, font=MAIN_FONT)
        sw_bo_qua.select()
        sw_bo_qua.pack(side="right")

        row2 = ctk.CTkFrame(card_data, fg_color="transparent")
        row2.pack(fill="x", padx=10, pady=5)
        ent_kw = ctk.CTkEntry(row2, width=220, placeholder_text="Từ khóa Web (VD: Gốc Đề)...", font=MAIN_FONT)
        ent_kw.pack(side="left", padx=(0, 10))
        cb_sap_xep = ctk.CTkOptionMenu(row2, values=["Bỏ qua Sắp xếp", "Tin nổi bật", "Mới đăng trước", "Giá thấp", "Giá cao", "Địa chỉ"], width=180, font=MAIN_FONT)
        cb_sap_xep.pack(side="left")

        row3 = ctk.CTkFrame(card_data, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=5)
        ent_gia = ctk.CTkEntry(row3, width=220, placeholder_text="Giá TỪ-ĐẾN (VD: 2tr-4tr)", font=MAIN_FONT)
        ent_gia.pack(side="left", padx=(0, 10))
        sw_tai_anh = ctk.CTkSwitch(row3, text="Tải ảnh phòng HD", progress_color=ACCENT_COLOR, font=MAIN_FONT)
        sw_tai_anh.select()
        sw_tai_anh.pack(side="left", padx=10)

        row4 = ctk.CTkFrame(card_data, fg_color="transparent")
        row4.pack(fill="x", padx=10, pady=5)
        cb_quan = ctk.CTkOptionMenu(row4, values=[
            "Bỏ qua Quận/Huyện", 
            "Cầu Giấy", "Đống Đa", "Hai Bà Trưng", 
            "Hoàng Mai", "Thanh Xuân", "Nam Từ Liêm", "Bắc Từ Liêm"
        ], width=130, font=MAIN_FONT)
        cb_quan.pack(side="left", padx=(0, 10))
        cb_nguon = ctk.CTkOptionMenu(row4, values=["Bỏ qua Nguồn", "Cầu Giấy", "Đống Đa", "Hà Đông", "Hoàng Mai", "Nam Từ Liêm", "Thanh Xuân"], width=130, font=MAIN_FONT)
        cb_nguon.pack(side="left", padx=(0, 10))
        cb_loai = ctk.CTkOptionMenu(row4, values=["Bỏ qua Loại Nhà", "Khép kín", "STUDIO", "1N1K", "2N1K", "Mặt bằng"], width=130, font=MAIN_FONT)
        cb_loai.pack(side="left")

        # KHUNG CUỘN DUY NHẤT TRONG APP (TIỆN ÍCH) -> MƯỢT 100% VÀ KHÔNG BỊ KẸT
        ctk.CTkLabel(card_data, text="Tiện ích & Yêu cầu:", font=MAIN_FONT).pack(anchor="w", padx=10, pady=(10, 0))
        frame_tien_ich = ctk.CTkScrollableFrame(card_data, height=180, fg_color="#2A2A38", corner_radius=10)
        frame_tien_ich.pack(fill="both", expand=True, padx=10, pady=5)
        
        tien_ich_dict = {
            "Thang máy": "Thang máy", "Thang bộ": "Thang bộ", "Đc nuôi pet": "Được nuôi pet", "Không pet": "Không nuôi pet",
            "Nhận xe điện": "Nhận xe điện", "Cấm xe điện": "Cấm xe điện", "Khách Q.Tế": "Nhận khách quốc tế", "Không Q.Tế": "Không khách quốc tế",
            "Ô tô vào nhà": "Ô tô vào nhà", "Gần bãi đỗ": "Gần bãi đỗ ô tô", "Gần đường lớn": "Gần đường lớn", "Chỉ VinFast": "Chỉ VinFast",
            "Có gác xép": "Có gác xép", "Không gác xép": "Không gác xép", "Ban công": "Ban công", "Điều hòa": "Điều hòa",
            "Nóng lạnh": "Nóng lạnh", "Giường": "Giường", "Giường tầng": "Giường tầng", "Tủ lạnh": "Tủ lạnh",
            "MG riêng": "Máy giặt riêng", "MG chung": "giặt chung", "MS chung": "sấy chung", "Thoát hiểm": "Thang thoát hiểm",
            "Bàn bếp": "Bàn bếp", "Tủ bếp": "Tủ bếp", "Bếp điện": "Bếp điện", "Hút mùi": "Hút mùi",
            "Wifi": "Wifi", "Tivi": "Tivi", "Sofa": "Sofa", "Bàn ghế": "Bàn ghế", "Tủ Q.Áo": "Tủ quần áo", "Đầu chờ MG": "Đầu chờ máy giặt"
        }
        
        checkbox_vars = {}
        for i, (display_name, raw_val) in enumerate(tien_ich_dict.items()):
            var = ctk.StringVar(value="")
            checkbox_vars[raw_val] = var
            cb = ctk.CTkCheckBox(frame_tien_ich, text=display_name, variable=var, onvalue=raw_val, offvalue="", font=MAIN_FONT, text_color=SUB_TEXT, checkbox_height=18, checkbox_width=18, fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER)
            cb.grid(row=i // 3, column=i % 3, padx=(5, 15), pady=8, sticky="w")

        card_zalo = ctk.CTkFrame(col_right, fg_color=CARD_COLOR, corner_radius=15)
        card_zalo.pack(fill="x", pady=(0, 10), ipadx=10, ipady=10)
        ctk.CTkLabel(card_zalo, text="💬 CHIẾN DỊCH ZALO & QR", font=H2_FONT, text_color="#00B894").pack(anchor="w", padx=10, pady=(0, 5))
        
        sw_zalo = ctk.CTkSwitch(card_zalo, text="Bật Auto Zalo", progress_color="#00B894", font=MAIN_FONT)
        sw_zalo.pack(anchor="w", padx=10, pady=5)
        ent_zalo_group = ctk.CTkEntry(card_zalo, width=350, placeholder_text="Tên nhóm Zalo...", font=MAIN_FONT)
        ent_zalo_group.pack(anchor="w", padx=10, pady=5)
        cb_zalo_mode = ctk.CTkOptionMenu(card_zalo, values=["Chạy Thật (2-5 phút)", "Test (10s/bài)"], button_color="#00B894", font=MAIN_FONT)
        cb_zalo_mode.pack(anchor="w", padx=10, pady=5)
        
        sw_qr = ctk.CTkSwitch(card_zalo, text="Auto Rải mã QR trên FB ( Kết hợp đăng bài trên Zalo )", progress_color="#00B894", font=MAIN_FONT)
        sw_qr.pack(anchor="w", padx=10, pady=(15, 5))
        ent_qr_group = ctk.CTkEntry(card_zalo, width=350, placeholder_text="Tên nhóm FB rải QR...", font=MAIN_FONT)
        ent_qr_group.pack(anchor="w", padx=10, pady=5)
        ent_qr_cap = ctk.CTkEntry(card_zalo, width=350, placeholder_text="Caption rải QR (Tùy chỉnh)...", font=MAIN_FONT)
        ent_qr_cap.pack(anchor="w", padx=10, pady=5)

        card_fb = ctk.CTkFrame(col_right, fg_color=CARD_COLOR, corner_radius=15)
        card_fb.pack(fill="x", pady=10, ipadx=10, ipady=10)
        ctk.CTkLabel(card_fb, text="📘 FACEBOOK & THỢ SĂN", font=H2_FONT, text_color="#0984E3").pack(anchor="w", padx=10, pady=(0, 5))
        
        sw_fb = ctk.CTkSwitch(card_fb, text="Bật Auto Post FB Group", progress_color="#0984E3", font=MAIN_FONT)
        sw_fb.pack(anchor="w", padx=10, pady=5)
        ent_fb_kws = ctk.CTkEntry(card_fb, width=350, placeholder_text="Từ khóa tìm Group FB (Cách bằng dấu phẩy)...", font=MAIN_FONT)
        ent_fb_kws.pack(anchor="w", padx=10, pady=5)

        ent_min_budget = ctk.CTkEntry(card_fb, width=350, placeholder_text="Bỏ qua khách có tài chính DƯỚI (VD: 3000000)...", font=MAIN_FONT)
        ent_min_budget.pack(anchor="w", padx=10, pady=5)
        
        row_hunter = ctk.CTkFrame(card_fb, fg_color="transparent")
        row_hunter.pack(fill="x", padx=10, pady=10)
        sw_hunter = ctk.CTkSwitch(row_hunter, text="Thợ Săn Kèm FB", progress_color="#FD79A8", font=MAIN_FONT)
        sw_hunter.pack(side="left")
        sw_hunter_dl = ctk.CTkSwitch(row_hunter, text="Thợ Săn Độc Lập", progress_color="#FD79A8", font=MAIN_FONT)
        sw_hunter_dl.pack(side="left", padx=15)
        
        cb_hunter_mode = ctk.CTkOptionMenu(card_fb, values=["Săn trên Newsfeed", "Săn trong Group"], button_color="#FD79A8", font=MAIN_FONT)
        cb_hunter_mode.pack(anchor="w", padx=10, pady=5)

        # NÚT ĐIỀU KHIỂN BÊN DƯỚI CÙNG CỘT PHẢI
        control_frame = ctk.CTkFrame(col_right, fg_color="transparent")
        control_frame.pack(fill="both", expand=True, padx=10, pady=10)

        def start_tool():
            # 1. TÀI KHOẢN
            self.user_email = ent_email.get().strip()
            self.user_pass = ent_pass.get().strip()
            self.user_phone = ent_phone.get().strip()
            if not self.user_email or not self.user_pass or not self.user_phone:
                mb.showerror("Thiếu thông tin", "Vui lòng nhập đầy đủ Tài khoản, Mật khẩu và Số điện thoại!")
                return

            # 2. XỬ LÝ LỌC
            try: self.num_rooms_to_scrape = int(ent_num_rooms.get() or 1)
            except: self.num_rooms_to_scrape = 1

            self.chay_ngam = False
            self.bo_qua_phong_cu = sw_bo_qua.get() == 1
            self.tu_khoa = ent_kw.get().strip()
            
            s = cb_sap_xep.get()
            self.sap_xep = s if s != "Bỏ qua Sắp xếp" else None
            q = cb_quan.get()
            self.quan_huyen = q if q != "Bỏ qua Quận/Huyện" else ""
            n = cb_nguon.get()
            self.nguon_hang = n if n != "Bỏ qua Nguồn" else ""
            l = cb_loai.get()
            self.loai_nha = l if l != "Bỏ qua Loại Nhà" else ""
            
            gia = ent_gia.get().strip().lower() 
            if '-' in gia:
                try:
                    self.gia_tu = gia.split('-')[0].strip()
                    self.gia_den = gia.split('-')[1].strip()
                except: pass
            elif gia.startswith('min'):
                # Lọc bỏ chữ "min", chỉ lấy ra các con số (VD: min 4.000.000 -> 4000000)
                self.gia_tu = "".join(filter(str.isdigit, gia))
                self.gia_den = ""
            elif gia.startswith('max'):
                self.gia_tu = "0"
                self.gia_den = "".join(filter(str.isdigit, gia))
            elif gia.isdigit(): 
                self.gia_tu = "0"
                self.gia_den = gia

            self.tien_ich_list = [raw_val for raw_val, var in checkbox_vars.items() if var.get() != ""]

            # 3. ZALO & QR
            self.dang_zalo = sw_zalo.get() == 1
            if self.dang_zalo:
                self.ten_nhom_zalo = ent_zalo_group.get().strip()
                self.zalo_delay_mode = 'test' if "Test" in cb_zalo_mode.get() else 'real'
                self.tai_anh = True
                
                self.spam_qr = sw_qr.get() == 1
                if self.spam_qr:
                    self.qr_path = os.path.abspath(os.path.join("KHO_ANH_HANOI_STAY", "qr.jpg"))
                    self.fb_group_spam = ent_qr_group.get().strip()
                    self.qr_captions_pool = [
                        "Bạn quét mã QR vào nhóm có nhiều phòng bạn cần tìm nha",
                        "Bạn quét mã QR trên ảnh để vào nhóm cập nhật phòng trống liên tục nhé!",
                        "Mình có nhóm Zalo chuyên phòng trọ khu vực này, bạn quét QR để tham khảo thêm nha.",
                        "Vào nhóm Zalo qua mã QR này để xem thêm nhiều phòng đẹp, giá tốt bạn nhé!",
                        "Bạn đang tìm phòng thì quét mã QR vào nhóm Zalo bên mình, có rất nhiều lựa chọn phù hợp đó ạ."
                    ]
                    cap = ent_qr_cap.get().strip()
                    if cap: self.qr_captions_pool.append(cap)
            else:
                self.tai_anh = sw_tai_anh.get() == 1
                self.spam_qr = False

            # 4. FACEBOOK & THỢ SĂN
            self.dang_fb = sw_fb.get() == 1
            mode_h = cb_hunter_mode.get()
            self.tho_san_mode = 'newsfeed' if "Newsfeed" in mode_h else 'group'

            # --- 2. LƯU MỨC GIÁ TỐI THIỂU VÀO ROBOT ---
            try:
                # Gọt sạch chữ cái, chỉ giữ lại số (VD: "3tr" -> 3000000 nếu nhập full)
                min_budget_str = "".join(filter(str.isdigit, ent_min_budget.get().strip()))
                self.hunter_min_budget = int(min_budget_str) if min_budget_str else 0
            except:
                self.hunter_min_budget = 0 # Nếu lỗi thì mặc định là 0 (Không lọc)
            # ------------------------------------------
            
            if self.dang_fb:
                self.fb_keyword = ent_fb_kws.get().strip()
                self.tho_san_fb = sw_hunter.get() == 1
                self.tho_san_doc_lap = False
                self.tai_anh = True
            else:
                self.tho_san_fb = False
                self.tho_san_doc_lap = sw_hunter_dl.get() == 1
                if self.tho_san_doc_lap:
                    self.fb_keyword = ent_fb_kws.get().strip()
                    self.tai_anh = True

            if self.num_rooms_to_scrape == 0:
                self.tho_san_doc_lap = True
                self.dang_zalo = False
                self.dang_fb = False
                self.tai_anh = True

            self.lich_su_phong = {}
            if self.bo_qua_phong_cu and os.path.exists(self.lich_su_file):
                with open(self.lich_su_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '|' in line:
                            parts = line.strip().split('|', 1) # Chỉ cắt ở dấu | đầu tiên
                            url, plat = parts[0].strip(), parts[1].strip()
                            if url not in self.lich_su_phong: self.lich_su_phong[url] = []
                            self.lich_su_phong[url].append(plat)

            app.quit()
            app.destroy()

        btn_start = ctk.CTkButton(
            control_frame, text="Khởi Động", 
            font=ctk.CTkFont(family=APPLE_FONT, size=20, weight="bold"), height=55, corner_radius=12,
            fg_color=ACCENT_COLOR, hover_color=ACCENT_HOVER, text_color="#FFFFFF",
            command=start_tool
        )
        btn_start.pack(side="left", fill="both", expand=True, padx=(0, 15))

        btn_exit = ctk.CTkButton(
            control_frame, text="ⓧ", width=55, height=55, corner_radius=27,
            fg_color="#3A3A4D", hover_color="#ED6A5E", text_color="#FFFFFF",
            font=ctk.CTkFont(family=APPLE_FONT, size=28, weight="bold"),
            command=lambda: self.force_exit(app)
        )
        btn_exit.pack(side="right")

        app.mainloop()
    
    def get_machine_hwid(self):
        # Lấy Serial Number của Mainboard và CPU (Rất khó giả mạo trên Windows)
        try:
            cmd_board = subprocess.Popen('wmic baseboard get serialnumber', shell=True, stdout=subprocess.PIPE)
            board_sn = cmd_board.communicate()[0].decode('utf-8').strip().split('\n')[1].strip()
            
            cmd_cpu = subprocess.Popen('wmic cpu get ProcessorId', shell=True, stdout=subprocess.PIPE)
            cpu_id = cmd_cpu.communicate()[0].decode('utf-8').strip().split('\n')[1].strip()
            
            # Trộn 2 mã lại và băm bằng SHA-256 để tạo ra HWID độc nhất
            raw_id = f"{board_sn}-{cpu_id}"
            hwid = hashlib.sha256(raw_id.encode()).hexdigest()[:20] # Lấy 20 ký tự cho gọn
            return hwid.upper()
        except Exception as e:
            return "UNKNOWN_HWID_ERROR"
    

    def check_hwid_security(self):
        import tkinter as tk
        from tkinter import messagebox
        import pyperclip

        my_hwid = self.get_machine_hwid()
        print(f"🔒 Hardware ID (Mã máy) của bạn là: {my_hwid}")
        
        base_url = os.getenv('FIREBASE_URL', "").rstrip('/')

        if not base_url:
            self.show_config_error()
            sys.exit()

        # Giữ nguyên URL quét nhánh tổng để kiểm định diện rộng ổn định nhất
        api_url = f"{base_url}/licenses.json"
        
        try:
            print("⏳ Đang kết nối tới Máy chủ kiểm định...")
            response = requests.get(api_url, timeout=10)
            license_data = response.json() if response.status_code == 200 else None
            
            if isinstance(license_data, dict):
                # --- LOGIC ĐỊNH ĐỒNG THÔNG MINH (HYBRID) ---
                # Trường hợp 1: Trả về cụm tổng (Chứa mã máy của bạn bên trong)
                if my_hwid in license_data:
                    user_data = license_data[my_hwid]
                # Trường hợp 2: Trả về cụm đơn lẻ (Nếu sau này bạn đổi URL về trỏ thẳng mã máy)
                elif "status" in license_data:
                    user_data = license_data
                else:
                    user_data = None
                # -------------------------------------------

                if isinstance(user_data, dict):
                    status_val = str(user_data.get("status", "")).strip(' "\'')
                    
                    if status_val == "active":
                        self.current_credits = int(user_data.get("credits", 0))
                        
                        if self.current_credits > 0:
                            print(f"✅ Máy chủ xác nhận: Kích hoạt thành công!")
                            print(f"💰 Số dư Token hiện tại: {self.current_credits:,}\n")

                            # Ghi log và chạy heartbeat
                            self.day_log_firebase(status="Active")
                            threading.Thread(target=self._heartbeat_loop, daemon=True).start()
                            return # Vượt qua bài kiểm tra thành công!
                        else:
                            self.show_license_error(my_hwid, "Tài khoản đã hết Token. Vui lòng nạp thêm!")
                    else:
                        self.show_license_error(my_hwid, "Tài khoản của bạn đang bị khóa hoặc ngưng kích hoạt!")
                else:
                    self.show_license_error(my_hwid, "Mã máy của bạn chưa được cấp phép trên hệ thống!")
            else:
                self.show_license_error(my_hwid, "Không thể đọc cấu trúc phản hồi từ máy chủ!")
                
        except Exception as e:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            messagebox.showwarning("⚠️ LỖI KẾT NỐI", f"Không thể kết nối máy chủ bản quyền.\nVui lòng kiểm tra mạng!")
            sys.exit()

    def show_config_error(self):
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        messagebox.showerror("❌ LỖI CẤU HÌNH", "Không tìm thấy FIREBASE_URL trong file .env!")

    def show_license_error(self, my_hwid, reason):
        import tkinter as tk
        from tkinter import messagebox
        import pyperclip
        pyperclip.copy(my_hwid)
        root = tk.Tk()
        root.withdraw() 
        root.attributes("-topmost", True)
        messagebox.showerror(
            "❌ LỖI BẢN QUYỀN", 
            f"{reason}\n\n"
            f"Mã máy (HWID) của bạn là: {my_hwid}\n\n"
            f"👉 MÃ MÁY ĐÃ ĐƯỢC TỰ ĐỘNG COPY.\n"
            f"Hãy gửi mã này cùng ảnh chụp chuyển khoản cho Admin để nạp Token nhé!"
        )
        sys.exit()
    
    def show_help_menu(self):
        print("\n" + "🌟"*30)
        print(" "*10 + "CẨM NANG SỬ DỤNG HANOI STAY PRO MAX")
        print("🌟"*30)
        
        print("\n⚠️ CẢNH BÁO QUAN TRỌNG NHẤT (VUI LÒNG ĐỌC KỸ):")
        print("   - Khi Robot đang chạy, TUYỆT ĐỐI KHÔNG thu nhỏ (Minimize), không phóng to")
        print("     hoặc đóng các cửa sổ/tab trình duyệt đang mở.")
        print("   - Không tự ý di chuột hoặc gõ phím vào cửa sổ mà Robot đang làm việc.")
        print("   - Việc can thiệp bằng tay có thể khiến Robot 'mù mắt' và gây gián đoạn chiến dịch!")

        print("\n🎯 1. [SỐ LƯỢNG PHÒNG CẦN QUÉT]")
        print("   - Cách dùng: Nhập một số nguyên (VD: 30) để cào data từ example-realestate.com.")
        print("   - Mẹo PRO: Nhập số '0' nếu bạn CHỈ MUỐN thả Thợ Săn lên FB tìm khách (Bỏ qua cào phòng).")
        
        print("\n♻️  2. [SỔ NAM TÀO - BỎ QUA PHÒNG CŨ]")
        print("   - Công dụng: Trí tuệ lõi chống Spam. Robot nhớ mặt những phòng ĐÃ TỪNG ĐĂNG")
        print("     để tự động bỏ qua, liên tục nạp phòng mới tinh cho bạn mỗi ngày.")
        
        print("\n⚙️  3. [CÁC BỘ LỌC TÌM KIẾM]")
        print("   - Cách dùng: Chọn số tương ứng hoặc nhập mức giá (VD: 2000000-4000000).")
        print("   - Bỏ trống (Bấm Enter) nếu bạn không muốn giới hạn tiêu chí đó.")
        
        print("\n💬 4. [AUTO ZALO CỘNG ĐỒNG]")
        print("   - Chế độ 't' (Test): Đăng tốc độ siêu tốc (15s/bài) để kiểm tra luồng.")
        print("   - Chế độ 'c' (Chạy thật): Tản nhiệt ngẫu nhiên 2-5 phút/bài chống khóa mồm Zalo.")
        
        print("\n📘 5. [AUTO FACEBOOK GROUP]")
        print("   - Cách dùng: Nhập nhiều từ khóa cách nhau bằng dấu phẩy (VD: Trọ Cầu Giấy, Tìm phòng).")
        print("   - Robot sẽ tự động lách Popup Ẩn danh, vượt giới hạn để Share chéo 9 nhóm/bài.")
        
        print("\n🕵️ 6. [THỢ SĂN VIP - ĐI TÌM KHÁCH MUA]")
        print("   - Đỉnh cao Công nghệ: Tự động tuần tra Newsfeed 24/7.")
        print("   - Dùng Trí tuệ nhân tạo (AI Gemini) phân tích budget, nhu cầu của khách.")
        print("   - Tự động nhảy vào web lục kho, bốc phòng, tải ảnh và thả Comment chốt Sale!")
        
        print("\n" + "🌟"*30)
        input("👉 Đã nắm vững quy tắc an toàn! Bấm [Enter] để bắt đầu thiết lập chiến dịch...")
    
    def init_driver(self):
        print("🌍 Khởi tạo Trình duyệt cho Nhiệm vụ Tương tác (FB, Zalo)...")
        edge_options = EdgeOptions()
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-dev-shm-usage")
        
        # --- THÊM 2 DÒNG NÀY ĐỂ TẮT TÍNH NĂNG QUÉT BẢO MẬT GÂY LAG CỦA EDGE ---
        edge_options.add_argument("--disable-features=msSmartScreenProtection")
        edge_options.add_argument("--disable-smartscreen")
        
        edge_options.add_argument(f"user-data-dir={os.path.abspath('Edge_Profile')}")
        edge_options.add_argument("--window-size=1920,1080")    
        self.driver = webdriver.Edge(options=edge_options)
        self.driver.maximize_window()
        self.wait = WebDriverWait(self.driver, 10)

    def login_auto(self):
        print("🔑 Đang khởi tạo phiên đăng nhập Hệ thống Mục tiêu...")
        try:
            self.driver.get("https://example-realestate.com/login-and-register/?tab=login")
            time.sleep(3) 
            if len(self.driver.find_elements(By.XPATH, "//input[@type='password']")) > 0:
                email_box = self.wait.until(EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Email') or @type='email' or contains(@name, 'user')]")))
                email_box.send_keys(self.user_email) # Đổi ở đây
                pass_box = self.driver.find_element(By.XPATH, "//input[@type='password' or contains(@placeholder, 'Mật khẩu')]")
                pass_box.send_keys(self.user_pass) # Đổi ở đây
                self.driver.find_element(By.XPATH, "//button[contains(., 'Đăng nhập') or @type='submit']").click()
                time.sleep(5)
                print("✅ Đăng nhập Hệ thống Mục tiêu thành công!")
            else:
                print("✅ Đã khôi phục phiên đăng nhập trước đó!")
        except Exception as e: print("⚠️ Lỗi biểu mẫu xác thực Hệ thống Mục tiêu!")

    def click_dropdown(self, text_to_find):
        try:
            el = self.driver.find_element(By.XPATH, f"//*[normalize-space(text())='{text_to_find}' or contains(text(), '{text_to_find}')]")
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", el)
            time.sleep(1.5)
            return True
        except: return False

    def apply_filters(self):
        print("⚙️ Đang áp dụng các bộ lọc...")

        # --- FIX: BÊ NGUYÊN THUẬT TOÁN DROP-DOWN CHUẨN TỪ THỢ SĂN XUỐNG ---
        def chon_box_listivo(ten_box, gia_tri):
            print(f"   -> Đang chọn {ten_box}: {gia_tri}...")
            try:
                # 1. Tìm và bấm mở Box
                box_xpath = f"//div[contains(@class, 'listivo-select-v2__placeholder') and contains(text(), '{ten_box}')]/.. | //*[contains(text(), '{ten_box}')]/parent::*//div[contains(@class, 'listivo-select')]"
                boxes = self.driver.find_elements(By.XPATH, box_xpath)
                
                if boxes:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", boxes[-1])
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].click();", boxes[-1])
                    time.sleep(2) # Chờ cái hộp rớt xuống

                    # 2. Quét chính xác option có tên giá trị để click
                    opt_xpath = f"//div[contains(@class, 'listivo-select-v2__dropdown')]//div[contains(text(), '{gia_tri}')]"
                    opts = self.driver.find_elements(By.XPATH, opt_xpath)
                    
                    clicked = False
                    for opt in reversed(opts): # Duyệt từ dưới lên để lấy option vừa mở
                        if opt.is_displayed():
                            self.driver.execute_script("arguments[0].click();", opt)
                            clicked = True
                            time.sleep(3.5) # Đợi web xoay load data
                            break
                            
                    if not clicked:
                        print(f"      ⚠️ Không nhấn được option '{gia_tri}' trong box {ten_box}.")
                else:
                    print(f"      ⚠️ Không tìm thấy BOX {ten_box} trên web.")
            except Exception as e:
                print(f"      ⚠️ Lỗi thao tác chọn {ten_box}: {e}")

        # GỌI HÀM XỬ LÝ QUẬN HUYỆN & NGUỒN HÀNG
        if self.quan_huyen:
            chon_box_listivo('Quận / Huyện', self.quan_huyen)

        if self.nguon_hang:
            chon_box_listivo('Nhóm Nguồn Hàng', self.nguon_hang)

        # -------------------------------------------------------------
        if self.sap_xep:
            try:
                sort_trigger = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".listivo-search-results__sort-by .listivo-select-v2__placeholder")))
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", sort_trigger)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", sort_trigger)
                time.sleep(1.5)
                options = self.driver.find_elements(By.XPATH, f"//*[contains(text(), '{self.sap_xep}')]")
                if options:
                    self.driver.execute_script("arguments[0].click();", options[-1])
                    time.sleep(3.5)
            except: pass

        if self.tu_khoa:
            try:
                kw_box = self.wait.until(
                    EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Từ khóa') or contains(@placeholder, 'Tìm kiếm') or @name='keyword']")))
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", kw_box)
                print("         -> Đang áp dụng từ khóa: " + self.tu_khoa)
                kw_box.clear()
                kw_box.send_keys(self.tu_khoa)
                kw_box.send_keys(Keys.ENTER)
                time.sleep(4) 
            except: pass

        if self.loai_nha:
            try:
                loai_nha_xpath = f"//div[contains(@class, 'listivo-search-panel__item-label') and contains(normalize-space(), '{self.loai_nha}')]"
                loai_nha_el = self.driver.find_element(By.XPATH, loai_nha_xpath)
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", loai_nha_el)
                self.driver.execute_script("arguments[0].click();", loai_nha_el)
                time.sleep(3.5)
            except: pass


        if self.loai_nha == "Bất kì" or not self.loai_nha:
            # --- NHẬP GIÁ TIỀN (LUÔN CHẠY NẾU CÓ NHẬP MENU) ---
            if getattr(self, 'gia_tu', '') or getattr(self, 'gia_den', ''):
                try:
                    last_box = None # Biến nhớ xem Robot vừa gõ vào ô nào cuối cùng
                    
                    if self.gia_tu and self.gia_tu != "0":
                        tu_box = self.driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Từ...')]")
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", tu_box)
                        tu_box.clear()
                        tu_box.send_keys(self.gia_tu)
                        last_box = tu_box  # Đánh dấu đã gõ vào ô Từ...
                        time.sleep(0.5)
                        
                    if getattr(self, 'gia_den', ''):
                        den_box = self.driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Đến...')]")
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", den_box)
                        den_box.clear()
                        den_box.send_keys(self.gia_den)
                        last_box = den_box # Đánh dấu đã gõ vào ô Đến...
                    
                    # Sau khi điền xong, ấn Enter ở đúng cái ô vừa gõ
                    if last_box:
                        last_box.send_keys(Keys.ENTER)
                        time.sleep(3.5) # Đợi web load danh sách
                except Exception as e:
                    print(f"      ⚠️ Lỗi điền giá: {e}")
        else:
            try:
                hien_thi_btns = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Hiển thị thêm') or contains(text(), 'Xem thêm')]")
                for btn in hien_thi_btns:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    self.driver.execute_script("arguments[0].click();", btn)
                    time.sleep(0.5)
            except: pass

            if self.tien_ich_list:
                for tien_ich in self.tien_ich_list:
                    try:
                        checkbox_xpath = f"//div[contains(@class, 'listivo-search-panel__item-label') and contains(normalize-space(), '{tien_ich}')]"
                        cb_el = self.driver.find_element(By.XPATH, checkbox_xpath)
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cb_el)
                        self.driver.execute_script("arguments[0].click();", cb_el)
                        time.sleep(2.5) 
                    except: pass

    def get_list_properties(self, num_rooms):
        # --- BƯỚC 1: ÉP TRẦN SỐ LƯỢNG KẾT QUẢ THỰC TẾ ---
        try:
            # Nhìn bằng "mắt thần" xem web báo có tổng cộng bao nhiêu kết quả
            count_els = self.driver.find_elements(By.XPATH, "//span[contains(@class, 'listivo-search-results__results-number-count')]")
            if count_els and count_els[0].is_displayed():
                total_text = count_els[0].text.strip()
                if total_text.isdigit():
                    total_available = int(total_text)
                    if num_rooms > total_available:
                        print(f"      ⚠️ Cảnh báo: Web chỉ có {total_available} kết quả. Tự động điều chỉnh mục tiêu xuống {total_available} phòng!")
                        num_rooms = total_available
                        self.num_rooms_to_scrape = total_available # Cập nhật luôn biến global
        except: pass

        property_links = []
        page = 1
        last_url = "" # Biến dùng để check kẹt trang
        
        while len(property_links) < num_rooms:
            print(f"--- Đang quét danh sách trang {page} ---")
            
            # --- BƯỚC 2: CHỐNG KẸT VÒNG LẶP (INFINITE LOOP) ---
            current_url = self.driver.current_url
            if current_url == last_url:
                print("⚠️ Đã đến trang cuối cùng (Không thể lật thêm trang). Dừng quét tại đây!")
                break
            last_url = current_url
            
            try:
                cards = self.wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.listivo-listing-card-v4")))
                for card in cards:
                    link = card.get_attribute('href')
                    if not link: continue
                    
                    phai_bo_qua = False
                    
                    # 1. BỘ LỌC SỔ NAM TÀO (Đã Up Bài)
                    da_up_o = self.lich_su_phong.get(link, []) if getattr(self, 'bo_qua_phong_cu', False) else []
                    if getattr(self, 'bo_qua_phong_cu', False) and link in self.lich_su_phong:
                        phai_bo_qua = True
                        if getattr(self, 'dang_zalo', False) and ('ZALO' not in da_up_o): phai_bo_qua = False 
                        if getattr(self, 'dang_fb', False) and ('FB' not in da_up_o): phai_bo_qua = False 
                            
                    if phai_bo_qua:
                        print(f"      ⏭️ Sổ Nam Tào: Phòng đã Up Bài. NHẢY CÓC!")
                        continue

                    # 2. BỘ LỌC SỔ TẢI ẢNH (Phòng đã có sẵn trong Kho Ảnh)
                    if getattr(self, 'tai_anh', False) and (link in self.danh_sach_da_tai_anh):
                        if not getattr(self, 'dang_zalo', False) and not getattr(self, 'dang_fb', False):
                            print(f"      ⏭️ Sổ Kho Ảnh: Phòng đã tải ảnh. NHẢY CÓC!")
                            continue
                    
                    # --- 3. BỘ LỌC SỔ ĐEN (BLACKLIST CỦA BẠN) ---
                    if getattr(self, 'blacklist_phong', set()) and link in self.blacklist_phong:
                        print(f"      🚫 Sổ Đen: Phát hiện phòng bị cấm. BỎ QUA NGAY!")
                        continue
                    # --------------------------------------------
                            
                    if link not in property_links:
                        property_links.append(link)
                        if len(property_links) == num_rooms: break
                
                if len(property_links) < num_rooms:
                    # --- NÂNG CẤP LƯỚT TRANG: TÌM CHÍNH XÁC NÚT NEXT ---
                    next_btns = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'listivo-pagination__item') and .//*[local-name()='svg']] | //div[contains(@class, 'listivo-pagination__item--next')]")
                    
                    if next_btns:
                        next_btn = next_btns[-1] 
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                        time.sleep(0.5)
                        self.driver.execute_script("arguments[0].click();", next_btn)
                        time.sleep(3.5) 
                        page += 1
                    else:
                        print("⚠️ Đã hết trang để quét! (Mất nút Next).")
                        break
            except TimeoutException: 
                print("⚠️ Không tìm thấy phòng nào phù hợp hoặc tải trang quá lâu.")
                break
                
        return property_links

    # BỘ LỌC ĐỊA CHỈ THÔNG MINH
    def format_short_address(self, title):
        if not title or title == "N/A": return "N/A"
        
        # 1. Cắt bỏ mọi thứ từ dấu '_' trở đi
        addr = title.split('_')[0].strip()
        
        # 2. Xóa chữ 'Số' hoặc 'Sô' ở đầu
        addr = re.sub(r'^[Ss][ốô]\s+', '', addr)
        
        # 3. Thay dấu '-' bằng ', '
        addr = addr.replace('-', ', ')
        
        # 4. Rút gọn số ngõ phức tạp (VD: 8.191.xx -> 8)
        addr = re.sub(r'^(\d+)[.,/][\da-zA-Z.,/]+\s+', r'\1 ', addr)
        
        # 5. Xóa các cụm từ thừa chủ nhà
        keywords = [' nhà ', ' chủ ', ' - ']
        addr_lower = addr.lower()
        for kw in keywords:
            if kw in addr_lower:
                idx = addr_lower.find(kw)
                addr = addr[:idx].strip()
                addr_lower = addr.lower()
                
        # 6. Xóa các đoạn trong ngoặc đơn (VD: "(trục 1,3)")
        addr = re.sub(r'\s*\(.*?\)', '', addr)
        
        return addr.strip()

    def download_images(self, img_urls, folder_name):
        if not img_urls: return
        save_path = os.path.abspath(os.path.join("KHO_ANH_HANOI_STAY", folder_name))
        
        # Tạo thư mục nếu chưa có
        if not os.path.exists(save_path): 
            os.makedirs(save_path)
            
        # 1. Lọc ra danh sách những ảnh CHƯA TỒN TẠI trong máy
        files_to_download = []
        for i, url in enumerate(img_urls):
            file_path = os.path.join(save_path, f"Anh_{i+1}.jpg")
            if not os.path.exists(file_path):
                files_to_download.append((file_path, url))
                
        # 2. Nếu tất cả ảnh đều đã có sẵn -> Bỏ qua bước tải
        if not files_to_download:
            print(f"      ⏭️ Đã có đủ ảnh phòng '{folder_name}'. Bỏ qua tải lại!")
            return
            
        # 3. Tiến hành tải các ảnh còn thiếu
        print(f"      ⬇️ Đang tải {len(files_to_download)} ảnh mới về thư mục '{folder_name}'...")
        for file_path, url in files_to_download:
            try:
                # Ép đuôi .jpg để Zalo hiển thị chuẩn Album
                response = requests.get(url, timeout=10)
                with open(file_path, 'wb') as f:
                    f.write(response.content)
            except: pass

    def extract_detail(self, url):
        #number = input("SĐT Của bạn: ").strip()
        self.driver.get(url)
        item_data = {}
        
        try: title = self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "h1.listivo-listing-name"))).text
        except: title = "N/A"
        try: price = self.driver.find_element(By.XPATH, "//div[@data-widget_type='lst_listing_price.default']").text.strip()
        except: price = "N/A"
        try:
            tags_el = self.driver.find_elements(By.CSS_SELECTOR, ".listivo-listing-attribute-v3")
            tags = ", ".join([t.text for t in tags_el if t.text])
        except: tags = "N/A"
        try: desc = self.driver.find_element(By.CSS_SELECTOR, ".listivo-listing-section__text").text
        except: desc = "N/A"
        try:
            features_el = self.driver.find_elements(By.CSS_SELECTOR, ".listivo-listing-feature__text")
            features_list = [f.text.strip() for f in features_el if f.text.strip()]
        except: features_list = []
        
        # =========================================================
        # QUÉT VÀ LỌC ẢNH (CHỈ LẤY 80% SỐ LƯỢNG)
        # =========================================================
        img_urls_list = []
        try:
            gallery_elements = self.driver.find_elements(By.CSS_SELECTOR, ".listivo-gallery-v2__image")
            for el in gallery_elements:
                hd_url = el.get_attribute('data-url')
                if hd_url and hd_url not in img_urls_list:
                    img_urls_list.append(hd_url)
            
            # --- CẮT GIẢM CÒN 80% ---
            tong_so_anh = len(img_urls_list)
            if tong_so_anh > 0:
                # Tính 80%, nhưng luôn giữ tối thiểu 3 ảnh (đề phòng phòng chỉ có 3-4 ảnh)
                so_luong_can_lay = max(3, int(tong_so_anh * 0.8))
                
                # Cắt mảng (Chỉ lấy từ đầu đến số lượng đã tính)
                img_urls_list = img_urls_list[:so_luong_can_lay]
                print(f"      📸 Web có {tong_so_anh} ảnh -> Đã lọc lấy {so_luong_can_lay} ảnh xịn nhất!")
                
        except: pass

        # Dùng bộ lọc chuẩn hóa địa chỉ
        short_address = self.format_short_address(title)
        
        # --- BƯỚC 1: FIX LỖI TRÙNG FOLDER 1N1K / 2N1K ---
        # Tìm xem trong tiêu đề hoặc mô tả có chữ 1n1k, 2n1k, 3n1k... không
        loai_phong_match = re.search(r'(\d[nN]\d[kK])', title + " " + tags + " " + desc)
        if loai_phong_match:
            # Nếu có, nối thêm vào đuôi địa chỉ ngắn để làm tên folder/tiêu đề mới
            short_address += f" - Phòng {loai_phong_match.group(1).upper()}"

        short_price = price
        if 'đ' in price.lower():
            p_num = price.lower().replace('đ', '').replace('.', '').strip()
            if p_num.isdigit():
                val = int(p_num)
                if val % 1000000 == 0: short_price = f"{val // 1000000}tr"
                elif val % 100000 == 0: short_price = f"{val // 1000000}tr{ (val % 1000000) // 100000 }"

        room_type = "studio khép kín" if "studio" in tags.lower() or "studio" in desc.lower() else "khép kín"
        
        # --- BƯỚC 2: TỐI ƯU HIỂN THỊ DIỆN TÍCH ---
        area_match = re.search(r'(\d+)\s*(m2|m²)', tags + " " + desc, re.IGNORECASE)
        area_str = ", rộng rãi" # Mặc định nếu không thấy số
        if area_match:
            area_val = int(area_match.group(1))
            if area_val >= 22:
                area_str = f", rộng {area_val}m2"
            else:
                area_str = "" # Dưới 22m2 thì giấu luôn chữ rộng đi

        features_lower = [f.lower() for f in features_list]
        has_balcony = any('ban công' in f for f in features_lower)
        has_window = any('cửa sổ' in f for f in features_lower) or 'cửa sổ' in desc.lower()
        
        extra_room_info = ""
        if has_balcony and has_window: extra_room_info = ", có ban công và cửa sổ thoáng"
        elif has_balcony: extra_room_info = ", có ban công thoáng"
        elif has_window: extra_room_info = ", có cửa sổ thoáng"

        exclude_words = ['ban công', 'cửa sổ', 'thang thoát hiểm', 'wifi']
        furn_items = [f for f in features_list if f.lower() not in exclude_words]
        if furn_items: furniture = ", ".join(furn_items)
        else:
            furn_match = re.search(r'(Nội thất[:\s]+)(.*?)(?=\n|$)', desc, re.IGNORECASE)
            furniture = furn_match.group(2).strip() if furn_match else "Cơ bản"

        # --- BƯỚC 3: THÊM THÔNG TIN THANG MÁY VÀO CẠNH PET ---
        pet = "Được nuôi pet" if "được nuôi pet" in tags.lower() else "Không nuôi pet"
        has_elevator = any('thang máy' in f for f in features_lower) or 'thang máy' in desc.lower()
        if has_elevator:
            pet += ", có thang máy"

        # =========================================================
        # TỔNG HỢP TIỆN ÍCH XUNG QUANH (TỪ DESC & TAGS_STR)
        # =========================================================
        nearby_info = []
        seen_lower = set() # Bộ lọc thông minh: Lưu chữ thường để chống trùng lặp tuyệt đối

        # 1. QUÉT TỪ MÔ TẢ (Thuật toán Gộp dòng thông minh)
        lines = [l.strip() for l in desc.split('\n') if l.strip()]
        skip_next = False
        
        for i, line in enumerate(lines):
            if skip_next:
                skip_next = False
                continue
                
            line_lower = line.lower()
            if any(kw in line_lower for kw in ['gần', 'cách', 'đh', 'đại học', 'trường', 'bx', 'bến xe']):
                clean_line = line.replace('-', '').replace('+', '').replace('•', '').strip()
                
                # Gộp dòng nếu kết thúc bằng ':'
                if clean_line.endswith(':') and i + 1 < len(lines):
                    next_line = lines[i+1].replace('-', '').replace('+', '').replace('•', '').strip()
                    if next_line and ':' not in next_line:
                        clean_line = f"{clean_line} {next_line}"
                        skip_next = True 
                        
                if clean_line and len(clean_line) < 80:
                    formatted_line = f"• {clean_line}"
                    check_dup = clean_line.lower() # Đưa về chữ thường để check
                    if check_dup not in seen_lower:
                        nearby_info.append(formatted_line)
                        seen_lower.add(check_dup)

        # 2. QUÉT TỪ TAGS (Radar mở rộng bắt những thứ desc bỏ sót)
        for tag in tags.split(','):
            tag = tag.strip()
            tag_lower = tag.lower()
            if any(kw in tag_lower for kw in ['gần trường', 'gần chợ', 'gần bãi', 'km', '~', 'cách']):
                clean_tag = tag.replace('-', '').replace('+', '').replace('•', '').strip()
                if clean_tag and len(clean_tag) < 80:
                    formatted_tag = f"• {clean_tag}"
                    check_dup = clean_tag.lower()
                    if check_dup not in seen_lower: # Chống trùng lặp chéo với mô tả
                        nearby_info.append(formatted_tag)
                        seen_lower.add(check_dup)

        # Chốt hạ: Chỉ lấy tối đa 5 địa điểm nổi bật nhất
        nearby_str = "\n".join(nearby_info[:5])

        # --- BƯỚC 4: TẠO 3 VĂN PHONG VÀ BỐC THĂM NGẪU NHIÊN ---
        # Xử lý phần text tiện ích xung quanh (Nếu có mới hiển thị)
        if nearby_str:
            nearby_0 = f"{nearby_str}\n\n"
            nearby_1 = f"{nearby_str}\n\n"
            nearby_2 = f"Vị trí thuận tiện đi lại:\n{nearby_str}\n\n"
        else:
            nearby_0 = nearby_1 = nearby_2 = ""

        vp0 = (f"{short_address}\n"
               f"-> Giá chỉ #{short_price}\n"
               f"- Phòng {room_type} siêu xinh{area_str}{extra_room_info}\n"
               f"- Nội thất: {furniture}\n"
               f"- {pet}\n\n"
               f"{nearby_0}"
               f"Ib mình hoặc {self.user_phone} (zalo) xem phòng free") # Đổi ở đây
        
        vp1 = (f"🔥 CỰC HOT: {short_address} 🔥\n"
               f"💰 Chốt nhanh chỉ với #{short_price}\n"
               f"✨ Dạng phòng: {room_type} xịn xò{area_str}{extra_room_info}.\n"
               f"🛋️ Đồ đạc sắm đủ: {furniture} - Xách vali vào là ở!\n"
               f"🐾 {pet}\n\n"
               f"{nearby_1}"
               f"👉 Nhanh tay Ib mình hoặc {self.user_phone} (zalo) để chốt phòng đi xem free nha!") # Đổi ở đây
        
        vp2 = (f"🏡 CHO THUÊ PHÒNG TẠI: {short_address}\n"
               f"💵 Mức giá vô cùng hợp lý: #{short_price}\n"
               f"🛏️ Thiết kế: {room_type} hiện đại{area_str}{extra_room_info}.\n"
               f"🚪 Căn hộ đã setup sẵn: {furniture}.\n"
               f"📌 Lưu ý: {pet}\n\n"
               f"{nearby_2}"
               f"📞 Anh/chị có nhu cầu Ib mình hoặc ib {self.user_phone} (zalo) để xem nhà hoàn toàn miễn phí ạ.") # Đổi ở đây

        vp3 = (f"🌟 TÌM TỔ ẤM KHU VỰC: {short_address} 🌟\n"
               f"💸 Trọn gói chỉ {short_price} - Giá quá sinh viên luôn!\n"
               f"✅ Không gian: {room_type} sạch đẹp{area_str}{extra_room_info}.\n"
               f"✅ Tiện nghi: {furniture} - Chỉ việc dọn quần áo tới ở.\n"
               f"✅ {pet}\n\n"
               f"{nearby_0}"
               f"💌 Các bạn quan tâm thì nhắn tin trực tiếp hoặc add Zalo {self.user_phone} mình dẫn đi xem phòng nhé!")

        vp4 = (f"⚡ GÓC PASS PHÒNG NHANH: {short_address}\n"
               f"💎 Tài chính: {short_price}\n"
               f"📌 Mô tả: Dạng {room_type}{area_str}{extra_room_info}. Đồ đạc bao gồm: {furniture}.\n"
               f"📌 Tình trạng pet: {pet}\n\n"
               f"{nearby_1}"
               f"Alo ngay Zalo {self.user_phone} hoặc inbox mình để giữ phòng nha mọi người.")

        vp5 = (f"🚨 PHÒNG ĐẸP NHANH HẾT TẠI {short_address} 🚨\n"
               f"💰 Giá hạt dẻ: {short_price}\n"
               f"🏢 Lên sóng căn {room_type} thiết kế cực chill{area_str}{extra_room_info}.\n"
               f"📺 Full đồ xịn: {furniture}.\n"
               f"🐈 Chú ý: {pet}\n\n"
               f"{nearby_2}"
               f"Chỉ còn đúng 1 phòng thôi ạ. Liên hệ ngay Zalo {self.user_phone} để chốt sớm nhé!")

        # Robot tung xúc xắc chọn ngẫu nhiên 1 trong 3 văn phong
        caption = random.choice([vp0, vp1, vp2, vp3, vp4, vp5])

        unique_id = url.strip('/').split('-')[-1][:4]
        folder_unique_name = f"{short_address} - {short_price} - {unique_id}"
        # Loại bỏ ký tự đặc biệt hợp lệ cho tên thư mục
        folder_unique_name = re.sub(r'[\\/*?:"<>|]', "", folder_unique_name).strip()

        item_data['Tiêu đề'] = title
        item_data['Địa chỉ ngắn'] = short_address # Lúc này địa chỉ ngắn đã chứa đuôi 1N1K
        item_data['Folder Ảnh'] = folder_unique_name # Lưu lại để dùng cho download và excel
        item_data['Giá'] = price
        item_data['Đặc điểm'] = tags
        item_data['Tiện ích'] = ", ".join(features_list) 
        item_data['Mô tả'] = desc
        item_data['Caption Auto'] = caption
        item_data['URL'] = url

        if self.tai_anh:
            self.download_images(img_urls_list, folder_unique_name)
            item_data['Link Ảnh'] = f"Đã tải về máy: KHO_ANH_HANOI_STAY/{folder_unique_name}"
            
            # TỰ ĐỘNG GHI URL VÀO SỔ TẢI ẢNH SAU KHI CHECK XONG
            if hasattr(self, 'danh_sach_da_tai_anh') and url not in self.danh_sach_da_tai_anh:
                self.danh_sach_da_tai_anh.add(url)
                with open(self.lich_su_anh_file, 'a', encoding='utf-8') as f:
                    f.write(f"{url}\n")
        else:
            item_data['Link Ảnh'] = " | ".join(img_urls_list)

        return item_data
    
    # ==============================================================
    # MODULE RẢI TỜ RƠI (CHỜ LOAD THÔNG MINH - FIX LỖI VỘI VÀNG)
    # ==============================================================
    # ==============================================================
    # MODULE RẢI TỜ RƠI (BÀO KIỆT THỜI GIAN ZALO & ĐẾM NGƯỢC TẢN NHIỆT)
    # ==============================================================
    def spam_comment_facebook_qr(self, available_time=0):
        import urllib.parse
        if not getattr(self, 'spam_qr', False) or not getattr(self, 'fb_group_spam', ''): return

        # Tính toán giờ "Giới nghiêm" (Trừ hao 20 giây để đóng tab, quay về Zalo an toàn)
        safe_end_time = time.time() + available_time - 20 if available_time > 30 else time.time() + 60

        try:
            # 1. Mở tab mới
            original_window = self.driver.current_window_handle
            self.driver.switch_to.new_window('tab') # Lệnh Native

            # 2. Mồi trang chủ FB
            print("      -> Đang mở trang chủ Facebook...")
            self.driver.get("https://www.facebook.com/")
            time.sleep(3)

            # 3. Ép URL tìm kiếm
            kw = self.fb_group_spam
            print(f"      -> Đang tìm kiếm sào huyệt: '{kw}'...")
            search_url = f"https://www.facebook.com/search/groups/?q={urllib.parse.quote(kw)}"
            self.driver.get(search_url)
            time.sleep(5) 
            
            # 4. Vào nhóm
            group_links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/groups/') and not(contains(@href, '/search/'))]")
            clicked = False
            for link in group_links:
                if link.is_displayed():
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link)
                    time.sleep(1)
                    self.driver.execute_script("arguments[0].click();", link)
                    clicked = True
                    break
                    
            if not clicked:
                print("      ⚠️ Không tìm thấy link nhóm. Rút lui.")
                self.driver.close()
                self.driver.switch_to.window(original_window)
                return
                
            print("      -> Đã vào sào huyệt, chờ tải trang và bài viết...")
            time.sleep(4)

            # 5. VÒNG LẶP RẢI BOM VẮT KIỆT THỜI GIAN
            success_count = 0
            current_idx = 0
            actions = ActionChains(self.driver)
            
            # Nếu thời gian hiện tại vẫn chưa đến "Giờ giới nghiêm" thì cứ tiếp tục rải
            while time.time() < safe_end_time:
                xpath_box = "//div[@role='textbox' and (contains(@aria-label, 'bình luận') or contains(@aria-label, 'Bình luận') or contains(@aria-label, 'comment'))]"
                write_boxes = self.driver.find_elements(By.XPATH, xpath_box)

                # Nếu đánh hết các ô bình luận nhìn thấy -> Mở thêm hoặc Cuộn trang load thêm
                if current_idx >= len(write_boxes):
                    cmt_btns = self.driver.find_elements(By.XPATH, "//*[text()='Bình luận' or text()='Comment']")
                    for btn in cmt_btns[current_idx : current_idx + 2]:
                        try:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                            time.sleep(1)
                            self.driver.execute_script("arguments[0].click();", btn)
                            time.sleep(1.5)
                        except: pass
                    
                    self.driver.execute_script("window.scrollBy(0, 1000);")
                    time.sleep(3)
                    
                    write_boxes = self.driver.find_elements(By.XPATH, xpath_box)
                    
                    # Nếu cuộn rồi mà vẫn không có thêm bài -> Nhóm hết bài -> Rút quân
                    if current_idx >= len(write_boxes):
                        print("      ⚠️ Đã vét sạch bài viết trong nhóm. Rút quân sớm.")
                        break

                try:
                    box = write_boxes[current_idx]
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", box)
                    time.sleep(1.5)
                    
                    try: box.click()
                    except: self.driver.execute_script("arguments[0].click();", box)
                    time.sleep(1)

                    # --- BƯỚC A: DÁN CHỮ ---
                    current_caption = random.choice(self.qr_captions_pool)
                    pyperclip.copy(current_caption)
                    actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(1.5)

                    # --- BƯỚC B: DÁN ẢNH ---
                    ps_paths = f"'{os.path.abspath(self.qr_path)}'"
                    subprocess.run(["powershell", "-command", f"Set-Clipboard -Path {ps_paths}"])
                    time.sleep(1.5)
                    actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(6)

                    # Nhấn Enter để gửi
                    actions.send_keys(Keys.ENTER).perform()
                    time.sleep(3)
                    success_count += 1
                    self.thong_ke['qr'] += 1 # Đếm số lượng QR
                    self.day_log_firebase(status="Active")
                    current_idx += 1

                    # --- NGHỈ NGƠI TẢN NHIỆT (ĐẾM NGƯỢC) ---
                    # Kiểm tra xem quỹ thời gian còn lại bao nhiêu
                    time_left = int(safe_end_time - time.time())
                    if time_left > 10:
                        # Tản nhiệt từ 30-90s, nhưng nếu thời gian còn lại ít hơn thì chỉ nghỉ bằng số tgian còn lại
                        wait_time = min(random.randint(45, 90), time_left)
                        print(f"      ⏳ Tản nhiệt {wait_time}s cho giống người thật...")
                        for remaining in range(wait_time, 0, -1):
                            mins, secs = divmod(remaining, 60)
                            print(f"\r      Đếm ngược tản nhiệt: {mins:02d}:{secs:02d} ", end="")
                            time.sleep(1)
                        print("\r" + " " * 50 + "\r", end="") # Xóa dòng đếm ngược cho gọn
                        
                except Exception as inner_e:
                    # Lỗi bài này thì tăng index để sang bài sau
                    current_idx += 1
            
            print(f"      ✅ Hết quỹ thời gian Zalo! Tổng kết thả thành công {success_count} chiếc QR.")

        except Exception as e:
            print(f"      ⚠️ Lỗi tổng khi rải QR FB: {type(e).__name__} trong khoảng thời gian {available_time}s")
        finally:
            # 7. Rút lui
            try:
                self.driver.close()
                self.driver.switch_to.window(original_window)
            except: pass

    # ==============================================================
    # MODULE AUTO POST ZALO V7.2 - FIX LỖI STALE ELEMENT & RỚT ẢNH
    # ==============================================================
    def auto_post_zalo(self):
        if not self.dang_zalo or not self.data:
            return

        print("\n" + "💬"*20)
        print("   BẮT ĐẦU CHIẾN DỊCH PHỦ SÓNG ZALO")
        print("💬"*20)
        
        self.driver.get("https://chat.zalo.me/")
        try:
            WebDriverWait(self.driver, 300).until(
                EC.presence_of_element_located((By.ID, "contact-search-input"))
            )
            print("✅ Đã đăng nhập Zalo Web thành công!")
        except:
            print("❌ Lỗi: Quá thời gian đăng nhập.")
            return

        time.sleep(3) 
        search_box = self.driver.find_element(By.ID, "contact-search-input")
        search_box.send_keys(self.ten_nhom_zalo)
        time.sleep(1); search_box.send_keys(Keys.ENTER); time.sleep(3) 

        actions = ActionChains(self.driver)
        
        for idx, item in enumerate(self.data):
            print(f"📦 Đang xử lý đăng bài [{idx + 1}/{len(self.data)}]...")

            # 1. DỌN KHUNG CHAT VÀ DÁN CAPTION TRƯỚC
            try:
                msg_box = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.ID, "richInput"))
                )
                msg_box.click()
                actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.BACK_SPACE).perform()
                time.sleep(0.5)
                # Thay SĐT linh hoạt
                zalo_caption = item['Caption Auto'].replace(f" {self.user_phone}", "")
                pyperclip.copy(zalo_caption) # Chú ý: Đổi item['Caption Auto'] thành zalo_caption
                actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                time.sleep(1) 
            except Exception as e:
                print("   ⚠️ Không thể thao tác với khung chat ban đầu.")
                continue

            # 2. COPY FILE ẢNH VÀO CLIPBOARD VÀ DÁN TRỰC TIẾP
            folder_name = item.get('Folder Ảnh', item['Tiêu đề'])
            save_path = os.path.abspath(os.path.join("KHO_ANH_HANOI_STAY", folder_name))

            if os.path.exists(save_path):
                all_imgs = [os.path.abspath(os.path.join(save_path, f)) for f in os.listdir(save_path) if f.lower().endswith('.jpg')]
                to_post = all_imgs[:max(3, int(len(all_imgs) * 0.5))]
                
                if to_post:
                    print(f"   -> Đang Copy {len(to_post)} file ảnh vào bộ nhớ đệm...")
                    try:
                        # Copy ảnh bằng PowerShell
                        ps_paths = ','.join([f"'{img}'" for img in to_post])
                        subprocess.run(["powershell", "-command", f"Set-Clipboard -Path {ps_paths}"])
                        time.sleep(1.5) 
                        
                        # FIX LỖI STALE: Tìm lại khung chat lần 2
                        msg_box_again = WebDriverWait(self.driver, 10).until(
                            EC.presence_of_element_located((By.ID, "richInput"))
                        )
                        msg_box_again.click()
                        
                        print("   -> Đang Paste (Ctrl+V) ảnh vào Zalo...")
                        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                        
                        print(f"   ⏳ Chờ Zalo load {len(to_post)} ảnh thành Album (15s)...")
                        time.sleep(15) 
                    except Exception as e:
                        print(f"   ⚠️ Lỗi khi Copy/Paste ảnh: {str(e)}")

            # 3. NHẤN ENTER CUỐI CÙNG ĐỂ GỬI TẤT CẢ (CHỮ + ALBUM)
            try:
                actions.send_keys(Keys.ENTER).perform() 
                print("   -> Đã bấm Gửi! Đang giữ mạng để Zalo đẩy ảnh đi (15s)...")
                time.sleep(15)
                print("   ✅ Đã ném bom thành công cả bộ!")
                self.thong_ke['zalo'] += 1 # Đếm số bài Zalo
                self.day_log_firebase(status="Active") 
                
                # BƯỚC MỚI: GHI SỔ NAM TÀO KÝ HIỆU ZALO
                url = item.get('URL', '')
                if getattr(self, 'bo_qua_phong_cu', False) and url:
                    with open(self.lich_su_file, 'a', encoding='utf-8') as f:
                        f.write(f"{url} | ZALO\n")
                    if url not in self.lich_su_phong: self.lich_su_phong[url] = []
                    self.lich_su_phong[url].append('ZALO')
            except:
                print("   ❌ Lỗi khi nhấn nút gửi cuối cùng.")

            # 4. CHỜ NGHỈ NGƠI
            if idx < len(self.data) - 1:
                delay = 15 if self.zalo_delay_mode == 'test' else random.randint(2 * 60, 5 * 60)
                
                if getattr(self, 'spam_qr', False) and os.path.exists(getattr(self, 'qr_path', '')):
                    print(f"\n   -> 🚀 TRANH THỦ COOLDOWN: Mở tab mới đi rải QR trên Facebook...")
                    start_time = time.time()
                    # Truyền quỹ thời gian Zalo đang có sang cho FB
                    self.spam_comment_facebook_qr(available_time=delay)
                    time_taken = int(time.time() - start_time)
                    
                    # Trừ đi số thời gian đã dùng để đi spam FB
                    delay = max(5, delay - time_taken) 
                    print(f"   -> 🛬 Đã về lại Zalo. Nghỉ ngơi nốt {delay} giây còn lại...")
                
                for remaining in range(delay, 0, -1):
                    mins, secs = divmod(remaining, 60)
                    print(f"\r      Đếm ngược nghỉ: {mins:02d}:{secs:02d} ", end="")
                    time.sleep(1)
                print("\r" + " " * 40 + "\r", end="")

        print("\n🎉 HOÀN TẤT TOÀN BỘ CHIẾN DỊCH ZALO!")

   # ==============================================================
    # MODULE AUTO POST FACEBOOK - ĐA TỪ KHÓA & TỐI ƯU 9 NHÓM
    # ==============================================================
    def auto_post_facebook(self):
        import subprocess
        if not getattr(self, 'dang_fb', False) or not self.data: return

        if getattr(self, 'current_credits', 0) < 2:
            print("\n❌ TÀI KHOẢN HẾT TIỀN: Không đủ 2 Token để chạy Đăng bài Group!")
            return
        
        print("\n" + "📘"*20 + "\n   BẮT ĐẦU CHIẾN DỊCH FACEBOOK\n" + "📘"*20)

        # Trích xuất danh sách từ khóa
        keywords_list = [k.strip() for k in self.fb_keyword.split(',') if k.strip()]
        first_keyword = keywords_list[0] if keywords_list else self.fb_keyword

        # 1. Mở trang chủ FB và chờ đăng nhập
        self.driver.get("https://www.facebook.com/")
        print("⏳ Đang chờ xác nhận đăng nhập Facebook (Tối đa 5 phút)...")
        try:
            search_input = WebDriverWait(self.driver, 300).until(
                EC.presence_of_element_located((By.XPATH, "//input[@aria-label='Tìm kiếm trên Facebook' or @type='search']"))
            )
            print("✅ Đã xác nhận phiên đăng nhập Facebook!")
        except:
            print("❌ Hết thời gian chờ đăng nhập Facebook. Hủy chiến dịch FB.")
            return

        time.sleep(3)

        # 2. Nhập từ khóa ĐẦU TIÊN, chờ Dropdown và vào Group
        print(f"🔍 Đang tìm kiếm Group theo từ khóa chính: '{first_keyword}'...")
        try:
            self.driver.execute_script("arguments[0].click();", search_input)
            time.sleep(1)
            search_input.send_keys(first_keyword)
            print("   -> Đợi Facebook hiển thị danh sách gợi ý...")
            time.sleep(4) 
            
            # MẮT THẦN DETECT LOGO VÀ ĐIỀU HƯỚNG BẰNG PHÍM CƠ
            suggestions = self.driver.find_elements(By.XPATH, "//ul[@role='listbox']//li[@role='presentation' or @role='row' or @role='option']")
            clicked = False
            
            # Dùng enumerate để lấy kèm vị trí (idx) của từng gợi ý (bắt đầu từ 0)
            for idx, sug in enumerate(suggestions):
                try:
                    logos = sug.find_elements(By.XPATH, ".//img | .//*[local-name()='image'] | .//*[local-name()='svg']")
                    text_content = sug.text.lower()
                    
                    if len(logos) > 0 and "nhóm" in text_content:
                        print(f"   -> 🎯 Đã detect Group ở vị trí số {idx + 1}. Đang dùng phím cơ để tiến vào...")
                        
                        # Vòng lặp bấm phím mũi tên xuống đúng bằng số vị trí của nó
                        for _ in range(idx + 1):
                            search_input.send_keys(Keys.ARROW_DOWN)
                            time.sleep(0.3) # Nghỉ một phần ba giây giữa mỗi lần bấm cho giống người
                            
                        # Sau khi di chuyển đúng vị trí, bấm Enter để chốt
                        time.sleep(0.5)
                        search_input.send_keys(Keys.ENTER)
                        
                        clicked = True
                        time.sleep(6) # Đợi trang Group tải xong
                        break
                except: pass
                
            # FALLBACK CHUẨN KHI KHÔNG TÌM THẤY
            if not clicked:
                print("   -> ⚠️ Không detect được Group có logo. Dùng phím điều hướng chọn cái đầu tiên...")
                search_input.send_keys(Keys.ARROW_DOWN)
                time.sleep(1)
                search_input.send_keys(Keys.ENTER)
                time.sleep(6)
                
        except Exception as e:
            print(f"❌ Lỗi khi tìm kiếm trên FB: {e}")
            return

        # --- CHỐT: ĐĂNG KÝ TAB GROUP VÀO SỔ TẬP TRUNG ---
        main_group_url = self.driver.current_url
        self.current_group_url = main_group_url
        self._tabs['fb_group'] = self.driver.current_window_handle
        print(f"   -> 📌 Đã lưu URL và đăng ký Tab Group an toàn!")

        actions = ActionChains(self.driver)

        # 4. Vòng lặp đăng bài
        for idx, item in enumerate(self.data):
            print(f"📦 Đang xử lý FB [{idx + 1}/{len(self.data)}]...")

            if idx > 0:
                print("   -> 🔄 Đang nạp lại trang Group để chuẩn bị nút đăng bài...")
                # DÙNG BỘ QUẢN LÝ TAB ĐỂ GỌI LẠI GROUP
                fb_group_tab = self._ensure_tab('fb_group', self.current_group_url)
                self.driver.switch_to.window(fb_group_tab)
                
                try:
                    self.driver.set_page_load_timeout(45)
                    self.driver.get(self.current_group_url)
                    time.sleep(5)
                except TimeoutException:
                    print("   ⚠️ Mạng giật lag, trang Group chưa tải xong 100% nhưng Robot ép chạy tiếp!")
                    try: self.driver.execute_script("window.stop();")
                    except: pass
                    time.sleep(2)
                except Exception as e_get:
                    print(f"   ⚠️ Lỗi tải trang không xác định, ép đi tiếp: {e_get}")    

            # Mở khung đăng bài
            try:
                write_btns = self.driver.find_elements(By.XPATH, "//span[contains(text(), 'Bạn viết gì đi...') or contains(text(), 'Viết gì đó...')]")
                if len(write_btns) > 0:
                    self.driver.execute_script("arguments[0].click();", write_btns[0])
                    time.sleep(4) 
                else:
                    print("⚠️ Không tìm thấy nút đăng bài. Bỏ qua.")
                    continue
            except Exception as e: continue

            # --- CHUẨN ĐOÁN & FIX LỖI: TÁCH TIÊU ĐỀ VÀ DÁN NỘI DUNG CHUẨN 100% (HYBRID) ---
            full_caption = item['Caption Auto']
            lines = full_caption.split('\n')
            
            fb_title = lines[0].strip()
            fb_body = '\n'.join(lines[1:]).strip()

            try:
                # BƯỚC 0: Đợi popup dialog đăng bài load xong hẳn
                try: 
                    WebDriverWait(self.driver, 10).until(
                        EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
                    )
                    time.sleep(1.5)
                except: pass

                # PHỤC HỒI CODE CŨ: Bắt chuẩn xác ô Tiêu đề bằng aria-label / placeholder
                title_xpath = "//*[contains(@aria-label, 'tiêu đề') or contains(@aria-label, 'Tiêu đề') or contains(@placeholder, 'tiêu đề') or contains(@placeholder, 'Tiêu đề')]"
                title_boxes = self.driver.find_elements(By.XPATH, title_xpath)
                
                # Lấy danh sách ô Title thực sự hiển thị trên màn hình
                visible_title_boxes = [b for b in title_boxes if b.is_displayed()]

                if len(visible_title_boxes) > 0:
                    print("   -> Phát hiện form có ô Tiêu Đề (Dùng Radar cũ). Đang dán tách biệt...")
                    
                    # 1. Click và dán Tiêu đề
                    title_box = visible_title_boxes[-1]
                    try: title_box.click()
                    except: self.driver.execute_script("arguments[0].click();", title_box)
                    time.sleep(1)
                    
                    pyperclip.copy(fb_title)
                    actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    time.sleep(1.5)

                    # 2. Tìm ô Nội dung (Loại trừ ô Tiêu đề) bằng logic cũ của bạn
                    print("   -> Đang chuyển focus và dán Nội dung...")
                    
                    # --- LỚP 1: SÁT THỦ ĐÓNG KHUNG CHAT ---
                    try:
                        chat_closes = self.driver.find_elements(By.XPATH,
                            "//div[@aria-label='Đóng đoạn chat' or "
                            "@aria-label='Close chat' or "
                            "@aria-label='Đóng cuộc trò chuyện' or "       # ← thêm
                            "@aria-label='Đóng hộp thư thoại' or "          # ← thêm  
                            "contains(@aria-label, 'Đóng hộp thư')]"
                            "[@role='button']"                               # ← thêm để tránh bắt nhầm
                        )
                        for btn in chat_closes: self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                    except: pass
                    
                    # --- LỚP 2: ÉP TÌM TEXTBOX BÊN TRONG BẢNG ĐĂNG BÀI (role='dialog') ---
                    all_textboxes = self.driver.find_elements(By.XPATH, "//div[@role='dialog']//div[@role='textbox'] | //div[@role='dialog']//div[@contenteditable='true']")
                    body_boxes = []
                    
                    for box in all_textboxes:
                        if box.is_displayed():
                            aria_label = (box.get_attribute("aria-label") or "").lower()
                            placeholder = (box.get_attribute("placeholder") or "").lower()
                            # Loại bỏ những ô có chứa chữ tiêu đề
                            if "tiêu đề" not in aria_label and "tiêu đề" not in placeholder:
                                body_boxes.append(box)
                    
                    if body_boxes:
                        target_body = body_boxes[-1] # Thường ô Nội dung nằm cuối cùng trong mảng
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target_body)
                        time.sleep(0.5)
                        
                        # ÉP FACEBOOK NHẬN FOCUS
                        try: target_body.click()
                        except: self.driver.execute_script("arguments[0].focus();", target_body)
                            
                        actions.move_to_element(target_body).click().perform() 
                        time.sleep(1.5)
                        
                        pyperclip.copy(fb_body)
                        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    else:
                        # Fallback cấp cứu: Nếu tịt ngòi XPath, mượn phím TAB để nhảy từ Tiêu đề xuống Nội dung
                        print("   ⚠️ Không tìm thấy ô Nội dung bằng XPath, dùng phím TAB để chuyển...")
                        actions.send_keys(Keys.TAB).perform()
                        time.sleep(1)
                        pyperclip.copy(fb_body)
                        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()

                else:
                    # Form gộp chung
                    print("   -> Form gộp chung. Đang dán Toàn bộ thông tin...")
                    # --- ĐÓNG CHAT BẢO VỆ FORM GỘP ---
                    try:
                        chat_closes = self.driver.find_elements(By.XPATH, "//div[@aria-label='Đóng đoạn chat' or @aria-label='Close chat' or contains(@aria-label, 'Đóng hộp thư')]")
                        for btn in chat_closes: self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(0.5)
                    except: pass

                    # Ép tìm trong dialog
                    general_boxes = self.driver.find_elements(By.XPATH, "//div[@role='dialog']//div[@role='textbox'] | //div[@role='dialog']//div[@contenteditable='true']")
                    visible_general = [box for box in general_boxes if box.is_displayed()]
                    
                    if visible_general:
                        target_box = visible_general[-1]
                        try: target_box.click()
                        except: self.driver.execute_script("arguments[0].focus();", target_box)
                        
                        actions.move_to_element(target_box).click().perform()
                        time.sleep(1)
                        pyperclip.copy(full_caption)
                        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                    else:
                        print("   ⚠️ Không tìm thấy ô nhập liệu nào trong dialog đăng bài!")
                
                time.sleep(2)
            except Exception as e:
                print(f"   ⚠️ Lỗi dán chữ: {e}")

            # ĐÍNH KÈM ẢNH
            folder_name = item.get('Folder Ảnh', item['Tiêu đề'])
            save_path = os.path.abspath(os.path.join("KHO_ANH_HANOI_STAY", folder_name))

            if os.path.exists(save_path):
                all_imgs = [os.path.abspath(os.path.join(save_path, f)) for f in os.listdir(save_path) if f.lower().endswith('.jpg')]
                to_post = all_imgs[:max(3, int(len(all_imgs) * 0.8))]

                if len(to_post) > 0:
                    print(f"   -> Đang tải {len(to_post)} ảnh lên Facebook...")
                    try:
                        ps_paths = ','.join([f"'{img}'" for img in to_post])
                        subprocess.run(["powershell", "-command", f"Set-Clipboard -Path {ps_paths}"])
                        time.sleep(1.5)
                        
                        # --- ĐÓNG CHAT BẢO VỆ LÚC DÁN ẢNH ---
                        try:
                            chat_closes = self.driver.find_elements(By.XPATH, "//div[@aria-label='Đóng đoạn chat' or @aria-label='Close chat' or contains(@aria-label, 'Đóng hộp thư')]")
                            for btn in chat_closes: self.driver.execute_script("arguments[0].click();", btn)
                            time.sleep(0.5)
                        except: pass

                        # Ép tìm trong dialog
                        body_boxes = self.driver.find_elements(By.XPATH, "//div[@role='dialog']//div[@role='textbox']")
                        if len(body_boxes) > 0:
                            self.driver.execute_script("arguments[0].click();", body_boxes[-1])
                            time.sleep(0.5)

                        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                        print("   ⏳ Chờ Facebook upload ảnh (15s)...")
                        time.sleep(15)
                    except: pass

            # TÍNH NĂNG THÊM NHÓM (QUÉT NHIỀU TỪ KHÓA)
            try:
                added_count = 0
                limit_reached = False # Biến cờ hiệu nhận biết FB chặn
                # --- TÍNH TOÁN NGÂN SÁCH ĐỘNG ---
                # Trừ 2 Token tiền đăng gốc, số dư còn lại chia 2 để ra số nhóm TỐI ĐA được phép tích
                max_groups_allowed = min(9, (getattr(self, 'current_credits', 0) - 2) // 2)
                if max_groups_allowed < 0: max_groups_allowed = 0
                
                if max_groups_allowed == 0:
                    print("   ⚠️ Ngân sách chỉ còn đủ đăng bài gốc, tự động chặn tính năng tích nhóm chéo!")
                else:
                    for kw in keywords_list:
                        if limit_reached or added_count >= 9:
                            break # Đã chạm nóc FB thì thoát luôn vòng lặp từ khóa
                            
                        print(f"   -> Đang xử lý chéo nhóm cho từ khóa: '{kw}'...")
                        
                        # 1. ĐẢM BẢO CỬA SỔ "THÊM NHÓM" ĐANG MỞ
                        search_xpath = "//div[@role='dialog']//input[@placeholder='Tìm kiếm nhóm' or @aria-label='Tìm kiếm nhóm']"
                        search_boxes = self.driver.find_elements(By.XPATH, search_xpath)
                        
                        if len(search_boxes) == 0 or not search_boxes[-1].is_displayed():
                            add_group_btns = self.driver.find_elements(By.XPATH, "//*[contains(text(), '+ Thêm nhóm') or contains(text(), 'Thêm nhóm')]")
                            if len(add_group_btns) > 0:
                                for btn in reversed(add_group_btns):
                                    if btn.is_displayed():
                                        print("   -> Mở danh sách Thêm Nhóm...")
                                        self.driver.execute_script("arguments[0].click();", btn)
                                        time.sleep(0.5)
                                        break
                        
                        # 2. GÕ TỪ KHÓA VÀO Ô TÌM KIẾM
                        try:
                            search_boxes = self.driver.find_elements(By.XPATH, search_xpath)
                            if len(search_boxes) > 0:
                                search_box = search_boxes[-1]
                                self.driver.execute_script("arguments[0].click();", search_box)
                                time.sleep(0.5)
                                
                                # Xóa sạch từ khóa cũ bằng Ctrl+A -> Backspace
                                search_box.send_keys(Keys.CONTROL + "a")
                                search_box.send_keys(Keys.BACKSPACE)
                                time.sleep(0.5)
                                
                                search_box.send_keys(kw)
                                time.sleep(4) # Chờ 4s để FB lọc danh sách
                            else:
                                print("   ⚠️ Không tìm thấy ô Tìm kiếm nhóm trong Popup.")
                                continue
                        except Exception as e_search:
                            print(f"   ❌ LỖI GÕ TỪ KHÓA: {type(e_search).__name__}")
                            continue

                        # 3. CHỌN NHÓM & XÁC MINH DẤU TÍCH XANH
                        try:
                            current_idx   = 0
                            max_attempts  = 15
                            stale_retries = 0  # Đếm số lần retry do stale

                            while (added_count < max_groups_allowed) and (current_idx < max_attempts) and not limit_reached:
                                try:
                                    xpath_cb = (
                                        "//div[@role='dialog']//div[@role='checkbox'] | "
                                        "//div[@role='dialog']//input[@type='checkbox']"
                                    )
                                    # LUÔN tìm lại cbs mới sau mỗi vòng lặp — tránh stale
                                    cbs = self.driver.find_elements(By.XPATH, xpath_cb)

                                    if current_idx >= len(cbs):
                                        print(f"   -> Đã duyệt hết danh sách nhóm cho từ khóa '{kw}'.")
                                        break

                                    cb = cbs[current_idx]

                                    # Bỏ qua nếu đã tích rồi
                                    if cb.get_attribute("aria-checked") == "true" or cb.get_attribute("checked"):
                                        current_idx += 1
                                        stale_retries = 0
                                        continue

                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cb)
                                    time.sleep(0.5)
                                    self.driver.execute_script("arguments[0].click();", cb)
                                    time.sleep(2)  # Chờ popup ẩn danh nổi lên (nếu có)

                                    # Xử lý popup ẩn danh
                                    anonymous_dialogs = self.driver.find_elements(
                                        By.XPATH, "//div[@role='dialog' and @aria-label='Bài viết ẩn danh']"
                                    )
                                    if anonymous_dialogs and anonymous_dialogs[-1].is_displayed():
                                        print("      -> ⚠️ Chạm trúng nhóm Ẩn danh. Đang ấn OK để đóng...")
                                        safe_btns = anonymous_dialogs[-1].find_elements(By.XPATH,
                                            ".//div[@role='button' and (@aria-label='OK' or @aria-label='Quay lại')] | "
                                            ".//span[text()='OK']/ancestor::div[@role='button']"
                                        )
                                        for btn in safe_btns:
                                            if btn.is_displayed():
                                                self.driver.execute_script("arguments[0].click();", btn)
                                                time.sleep(1.5)
                                                break
                                        # Nhóm ẩn danh → không được tích → next
                                        current_idx += 1
                                        stale_retries = 0
                                        continue

                                    # Verify tích xanh — tìm lại cbs vì DOM có thể đã thay đổi
                                    time.sleep(0.5)
                                    cbs_verify = self.driver.find_elements(By.XPATH, xpath_cb)
                                    if current_idx < len(cbs_verify):
                                        cb_verify = cbs_verify[current_idx]
                                        if cb_verify.get_attribute("aria-checked") == "true" or cb_verify.get_attribute("checked"):
                                            added_count += 1
                                            print(f"      -> ✅ Tích nhóm {added_count}/9 thành công!")
                                        else:
                                            # Kiểm tra FB có báo hết lượt không
                                            limit_msgs = self.driver.find_elements(By.XPATH,
                                                "//*[contains(text(), 'giới hạn chia sẻ') or "
                                                "contains(text(), 'đạt giới hạn')]"
                                            )
                                            if limit_msgs:
                                                print("      -> ⚠️ FB Đã chặn! Đạt giới hạn tối đa nhóm chéo.")
                                                limit_reached = True
                                                break

                                    current_idx  += 1
                                    stale_retries = 0  # Reset counter sau mỗi lần thành công

                                except StaleElementReferenceException:
                                    stale_retries += 1
                                    if stale_retries >= 3:
                                        # Stale quá 3 lần liên tiếp → DOM bị lỗi, thoát từ khóa này
                                        print(f"   ⚠️ DOM bị stale liên tục, bỏ qua từ khóa '{kw}'.")
                                        break
                                    # Stale 1-2 lần → thử lại ĐÚNG index đó, không tăng current_idx
                                    print(f"      -> 🔄 DOM stale, thử lại index {current_idx}...")
                                    time.sleep(1)
                                    continue  # Lặp lại với cùng current_idx

                                except Exception as e_inner:
                                    print(f"   ⚠️ Lỗi tại index {current_idx}: {type(e_inner).__name__}")
                                    current_idx  += 1
                                    stale_retries = 0

                        except Exception as e_cb:
                            print(f"   ⚠️ Lỗi tổng quát từ khóa '{kw}': {type(e_cb).__name__}")

                print(f"   ✅ Tổng kết: Đã tích chọn {added_count} nhóm chéo thành công!")
                
                # 4. BẤM NÚT "XONG" (FIX CHUẨN XPATH)
                try:
                    print("   -> Đang tiến hành bấm nút XONG...")
                    xong_clicked = False
                    
                    # Ưu tiên bắt thẳng vào cái chữ Xong trong nút màu xanh
                    xong_spans = self.driver.find_elements(By.XPATH, "//div[@role='dialog']//span[text()='Xong']")
                    if len(xong_spans) > 0:
                        self.driver.execute_script("arguments[0].click();", xong_spans[-1])
                        xong_clicked = True
                    else:
                        xong_divs = self.driver.find_elements(By.XPATH, "//div[@role='dialog']//div[@aria-label='Xong' and @role='button']")
                        if len(xong_divs) > 0:
                            self.driver.execute_script("arguments[0].click();", xong_divs[-1])
                            xong_clicked = True
                            
                    if xong_clicked:
                        print("   -> Đã bấm XONG. Chờ đóng bảng chọn nhóm...")
                        time.sleep(3)
                    else:
                        print("   ❌ Không tìm thấy nút XONG hiển thị để bấm.")
                except Exception as e_xong:
                    print(f"   ⚠️ Lỗi thao tác nút XONG: {type(e_xong).__name__}")
                    
            except Exception as e: 
                print(f"   ❌ Lỗi TỔNG MODULE NHÓM: {type(e).__name__}")

            # BẤM NÚT ĐĂNG
            try:
                post_btns = self.driver.find_elements(By.XPATH, "//div[@aria-label='Đăng' and @role='button']")
                clicked = False
                for btn in reversed(post_btns):
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        clicked = True
                        break
                
                if clicked:
                    print("   -> Đã bấm Đăng! Chờ hệ thống đẩy bài (15s)...")
                    # --- TÍNH TOÁN SỐ LƯỢNG VÀ SỐ TIỀN THỰC TẾ ---
                    tong_bai = 1 + added_count # 1 bài gốc + số nhóm đã tích thành công
                    tong_token = tong_bai * 2  # Đồng giá 2 Token / Bài
                    
                    print(f"   ✅ Lên bài Facebook thành công! (Tổng cộng {tong_bai} bài)")
                    self.thong_ke['fb'] += tong_bai # Nhảy số liệu chính xác để báo cáo
                    self.day_log_firebase(status="Active")
                    
                    # ---> THU PHÍ ĐĂNG BÀI FB THEO HỆ SỐ <---
                    self.tru_token_firebase(tong_token, f"Đăng {tong_bai} bài FB Group")
                    if getattr(self, 'current_credits', 0) < 2:
                        print("   🛑 BÁO ĐỘNG: Tài khoản không đủ 2 Token. Hủy các bài đăng còn lại!")
                        return # Rút lui ngay lập tức
                    # ------------------------------
                    
                    # BƯỚC MỚI: GHI SỔ NAM TÀO KÝ HIỆU FB
                    url = item.get('URL', '')
                    if getattr(self, 'bo_qua_phong_cu', False) and url:
                        with open(self.lich_su_file, 'a', encoding='utf-8') as f:
                            f.write(f"{url} | FB\n")
                        if url not in self.lich_su_phong: self.lich_su_phong[url] = []
                        self.lich_su_phong[url].append('FB')
                else:
                    print("   ❌ Không tìm thấy nút Đăng hiển thị (Có thể bảng Thêm nhóm chưa đóng kịp).")
            except Exception as e:
                print(f"   ❌ Lỗi bấm ĐĂNG: {type(e).__name__}")

            # COOLDOWN CHỐNG SPAM
            # COOLDOWN FB & BẬT THỢ SĂN
            if idx < len(self.data) - 1:
                delay = 30 if self.zalo_delay_mode == 'test' else random.randint(10 * 60, 15 * 60)
                
                # NẾU BẬT THỢ SĂN -> Dành quỹ thời gian cho Thợ Săn chạy
                if getattr(self, 'tho_san_fb', False):
                    start_hunt = time.time()
                    # Truyền thêm cờ is_standalone=False để Robot biết đây là chạy kết hợp
                    self.hunt_customers_facebook(available_time=delay, is_standalone=False)
                    time_used = int(time.time() - start_hunt)
                    delay = max(10, delay - time_used) # Tính toán thời gian dư còn lại

                # Đếm ngược thời gian dư (nếu có)
                print(f"      ⏳ Bắt đầu thời gian Cooldown nghỉ ngơi ({delay} giây) để tránh checkpoint FB...")
                for remaining in range(delay, 0, -1):
                    mins, secs = divmod(remaining, 60)
                    # Chỉ in ra log mỗi 15 giây hoặc 5 giây cuối cùng để tránh rác Mini HUD
                    if remaining % 15 == 0 or remaining <= 5:
                        print(f"         -> Còn lại: {mins:02d} phút {secs:02d} giây...")
                    time.sleep(1)
                print("      ✅ Đã xong Cooldown! Chuẩn bị đăng bài tiếp theo...")

    def run_standalone_hunter(self):
        if not getattr(self, 'tho_san_doc_lap', False): return
        print("\n" + "🎯"*20 + "\n   BẮT ĐẦU CHIẾN DỊCH THỢ SĂN ĐỘC LẬP\n" + "🎯"*20)

        self.driver.get("https://www.facebook.com/")
        print("⏳ Đang chờ xác nhận đăng nhập Facebook (Tối đa 5 phút)...")
        try:
            search_input = WebDriverWait(self.driver, 300).until(
                EC.presence_of_element_located((By.XPATH, "//input[@aria-label='Tìm kiếm trên Facebook' or @type='search']"))
            )
            print("✅ Đã xác nhận phiên đăng nhập Facebook!")
        except:
            print("❌ Hết thời gian chờ đăng nhập Facebook. Hủy chiến dịch.")
            return

        time.sleep(3)
        
        # Nếu săn trong Group thì mới chạy đi search
        if getattr(self, 'tho_san_mode', 'group') == 'group':
            kw = self.fb_keyword
            print(f"🔍 Đang tìm kiếm Group sào huyệt: '{kw}'...")
            try:
                self.driver.execute_script("arguments[0].click();", search_input)
                time.sleep(1)
                search_input.send_keys(kw)
                print("   -> Đợi Facebook hiển thị danh sách gợi ý...")
                time.sleep(4) 
                
                # MẮT THẦN DETECT LOGO VÀ ĐIỀU HƯỚNG BẰNG PHÍM CƠ
                suggestions = self.driver.find_elements(By.XPATH, "//ul[@role='listbox']//li[@role='presentation' or @role='row' or @role='option']")
                clicked = False
                
                # Dùng enumerate để lấy kèm vị trí (idx) của từng gợi ý (bắt đầu từ 0)
                for idx, sug in enumerate(suggestions):
                    try:
                        logos = sug.find_elements(By.XPATH, ".//img | .//*[local-name()='image'] | .//*[local-name()='svg']")
                        text_content = sug.text.lower()
                        
                        if len(logos) > 0 and "nhóm" in text_content:
                            print(f"   -> 🎯 Đã detect Group ở vị trí số {idx + 1}. Đang dùng phím cơ để tiến vào...")
                            
                            # Vòng lặp bấm phím mũi tên xuống đúng bằng số vị trí của nó
                            for _ in range(idx + 1):
                                search_input.send_keys(Keys.ARROW_DOWN)
                                time.sleep(0.3) # Nghỉ một phần ba giây giữa mỗi lần bấm cho giống người
                                
                            # Sau khi di chuyển đúng vị trí, bấm Enter để chốt
                            time.sleep(0.5)
                            search_input.send_keys(Keys.ENTER)
                            
                            clicked = True
                            time.sleep(6) # Đợi trang Group tải xong
                            break
                    except: pass
                    
                # FALLBACK CHUẨN KHI KHÔNG TÌM THẤY
                if not clicked:
                    print("   -> ⚠️ Không detect được Group có logo. Dùng phím điều hướng chọn cái đầu tiên...")
                    search_input.send_keys(Keys.ARROW_DOWN)
                    time.sleep(1)
                    search_input.send_keys(Keys.ENTER)
                    time.sleep(6)
            except Exception as e:
                print(f"❌ Lỗi khi tìm kiếm sào huyệt trên FB: {e}")
                return
        else:
            print("   -> Đã thâm nhập News Feed thành công!")
            
        print("   -> Thiết lập thời gian săn...")
        try:
            so_gio = float(input("   ⏱️ Bạn muốn Thợ Săn cắm trại trong bao nhiêu giờ? Mặc định là 1 tiếng (VD: 1.5): ").strip())
            thoi_gian_san = int(so_gio * 3600)
        except:
            thoi_gian_san = 3600 
            
        self.hunt_customers_facebook(available_time=thoi_gian_san, is_standalone=True)
        
    # ==============================================================
    # MODULE THỢ SĂN V21.0 (GIỮ 1 TAB + NỚI TRẦN NGÂN SÁCH THÔNG MINH)
    # ==============================================================
    def hunt_customers_facebook(self, available_time, is_standalone=False):
        if getattr(self, 'current_credits', 0) < 2:
            print("\n❌ TÀI KHOẢN HẾT TIỀN: Không đủ 2 Token để mở chế độ Thợ Săn!")
            return
        
        safe_end_time = time.time() + available_time - 20
        print("\n   -> 🕵️ BẬT CHẾ ĐỘ THỢ SĂN: Sắp xếp Mới Đăng & Nới Trần Tự Động...")

        # BẢN ĐỒ ĐỊA LÝ ĐA TẦNG (1 NHÓM TỪ KHÓA -> NHIỀU KHU VỰC VỆ TINH)
        loc_map = {
            # --- 1. NHÓM TRƯỜNG ĐẠI HỌC (Khu vực Cầu Giấy / Đống Đa) ---
            'sư phạm | hnue | ajc | báo chí | học viện báo chí | ulis | vnu | đại học quốc gia | xuân thủy | đại học ngoại ngữ': ['Trần Quốc Vượng', 'Mai Dịch', 'Dịch Vọng Hậu', 'Trần Cung', 'Hoàng Quốc Việt', 'Phạm Văn Đồng', 'Cầu Giấy'],
            'ngoại thương | học viện ngoại giao | ftu | dav | hv ngoại giao | hvng': ['Chùa Láng', 'Nguyễn Chí Thanh', 'Láng', 'Đống Đa'],
            'utc | giao thông vận tải | gtvt': ['Láng', 'Chùa Láng', 'Cầu Giấy', 'Đống Đa'],
            'đê la thành | đê la thanh | la thành': ['Đê La Thành', 'Giảng Võ', 'Ô Chợ Dừa', 'Thành Công', 'Đống Đa', 'Ba Đình'],
            
            # --- 2. NHÓM TRƯỜNG ĐẠI HỌC (Khu vực Từ Liêm / Hoài Đức) ---
            'tmu | đh thương mại | đại học thương mại | thương mại': ['Cầu Diễn', 'Hồ Tùng Mậu', 'Phạm Văn Đồng', 'Mai Dịch', 'Nam Từ Liêm'],
            'haui | đh công nghiệp | đại học công nghiệp | đh đông á | tài nguyên môi trường | tài nguyên & môi trường | cao đẳng fpt': ['Nhổn', 'Kiều Mai', 'Phú Diễn', 'Phương Canh', 'Nam Từ Liêm', 'Bắc Từ Liêm'],
            'hvtc | học viện tài chính | aof | mỏ | humg': ['Đông Ngạc', 'Cổ Nhuế', 'Bắc Từ Liêm'],

            'định công | định công hạ | định công hạ': ['Định Công', 'Đại Kim', 'Hoàng Mai', 'Thanh Xuân'],
            'tam trinh': ['Tam Trinh', 'Mai Động', 'Minh Khai', 'Hoàng Mai', 'Hai Bà Trưng'],

            # --- 3. NHÓM TRƯỜNG ĐẠI HỌC (Khu vực Hai Bà Trưng / Hoàng Mai / Thanh Xuân) ---
            'bkx | bách khoa | bách kinh xây | xây dựng | kinh tế quốc dân | hust | neu | huce | Bách - Kinh - Xây': ['Bách kinh xây', 'Phan Đình Giót', "Đình Đông", 'Giải Phóng', 'Hai Bà Trưng', 'Đống Đa'],
            'uneti | hubt | kinh kỹ | kinh công | kinh doanh công nghệ | kinh tế kỹ thuật công nghiệp': ['LN', 'Lĩnh Nam', 'Nam Dư', 'Kim Giang', 'Vĩnh Tuy', 'Minh Khai', 'Mai Động', 'Hoàng Mai', 'Hai Bà Trưng'],
            'trung kính | trung hòa': ['Trung Kính', 'Trung Hòa', 'Yên Hòa', 'Cầu Giấy'],
            'đại mỗ | vincom mega mall smart city': ['Đại Mỗ', 'Nam Từ Liêm', 'Hà Đông'],
            'tây mỗ | đại nam': ['Tây Mỗ', 'Nam Từ Liêm', 'Hà Đông'],
            'triều khúc | eco green city | riverside garden | k tân triều | đại học hà nội | hanu | đhhn | utt | công nghệ giao thông vận tại | cngtvt | công nghệ gtvt | hvan | học viện an ninh | kỹ thuật mật mã | kma | hvktmm | quản lý giáo dục ': ['triều khúc', 'Nam Từ Liêm', 'Hà Đông'],
            'tân triều | eco green city | riverside garden | k tân triều | đại học hà nội | hanu | đhhn | utt | công nghệ giao thông vận tại | cngtvt | công nghệ gtvt | hvan | học viện an ninh | kỹ thuật mật mã | kma | hvktmm | quản lý giáo dục': ['tân triều', 'Nam Từ Liêm', 'Hà Đông'],
            'văn quán': ['văn quán', 'Hà Đông'],
            'phùng khoang | đại học hà nội | k tân triều | hanu | đhhn | utt | công nghệ giao thông vận tại | cngtvt | công nghệ gtvt | hvan | học viện an ninh | kỹ thuật mật mã | kma | hvktmm | quản lý giáo dục': ['Phùng Khoang', 'Hà Đông'],

            # [MỚI] BỔ SUNG NHÓM THANH XUÂN (Theo ý tưởng của bạn + Mở rộng)
            'cao đẳng y hà nội | cđ y hà nội | đại học thăng long | tlu | đhkhtn | đại học khoa học tự nhiên | khoa học tự nhiên | hus | ussh | nhân văn | đại học khoa học xã hội': ['Kim Giang', 'Bùi Xương Trạch', 'Khương Đình', 'Phan Trọng Tuệ', 'Bằng Liệt', 'Triều Khúc', 'Thanh Xuân'],
            
            # [MỚI] TẶNG KÈM NHÓM HÀ ĐÔNG (Cực nhiều khách)
            'ptit | kiến trúc | hau | bưu chính viễn thông | an ninh | c500 | y dược cổ truyền | y cổ truyền': ['Mộ Lao', 'Văn Quán', 'Ao Sen', 'Phùng Khoang', 'Triều Khúc', 'Hà Đông'],

            # --- 4. NHÓM KHU ĐÔ THỊ / ĐƯỜNG / PHƯỜNG / BẾN XE ---
            # [MỚI] BỔ SUNG MỸ ĐÌNH & NGÃ TƯ SỞ
            'bx mỹ đình | bến xe mỹ đình | bxmd | bx md': ['Đình Thôn', 'Trần Bình', 'Mỹ Đình', 'Lê Đức Thọ', 'Nam Từ Liêm'],
            'ngã tư sở | nts': ['Khương Trung', 'Vĩnh Hồ', 'Thái Thịnh', 'Vương Thừa Vũ', 'Vũ Tông Phan', 'Đống Đa', 'Thanh Xuân'],
            
            'ngoại giao đoàn | thành phố giao lưu | tp giao lưu': ['Cổ Nhuế', 'Xuân Đỉnh', 'Bắc Từ Liêm'],
            'cổ nhuế | tăng thiết giáp | nghĩa đô': ['Cổ Nhuế', 'Đông Ngạc', 'Phạm Văn Đồng', 'Bắc Từ Liêm'],
            'phạm văn đồng': ['Phạm Văn Đồng', 'Cổ Nhuế', 'Bắc Từ Liêm'],
            'trần cung | hoàng quốc việt | hqv': ['Trần cung', 'Cổ Nhuế'],
            'đông ngạc': ['Đông Ngạc', 'Cổ Nhuế', 'Bắc Từ Liêm'],
            'xuân đỉnh': ['Xuân Đỉnh', 'Cổ Nhuế', 'Bắc Từ Liêm'],
            'mễ trì': ['Mễ Trì', 'Mỹ Đình', 'Nam Từ Liêm'],
            'kim ngưu': ['Kim Ngưu', 'Hai Bà Trưng'],
            'gốc đề': ['Gốc Đề', 'Hoàng Mai', 'Hai Bà Trưng'],

            # --- 5. NHÓM QUẬN/HUYỆN (Kích hoạt chế độ chọn Box thả xuống) ---
            'hoài đức': ['Hoài Đức'], 'thanh trì': ['Thanh Trì'], 'ba đình': ['Ba Đình'],
            'cầu giấy': ['Cầu Giấy'], 'đống đa': ['Đống Đa'], 'hà đông': ['Hà Đông'],
            'hai bà trưng': ['Hai Bà Trưng'], 'hoàng mai': ['Hoàng Mai'], 'tây hồ': ['Tây Hồ'],
            'thanh xuân': ['Thanh Xuân'], 'hoàn kiếm': ['Hoàn Kiếm'], 'long biên': ['Long Biên'],
            'nam từ liêm': ['Nam Từ Liêm'], 
            'bắc từ liêm': ['Bắc Từ Liêm']
        }

        # TRẢ LẠI BLACKLIST CŨ BẮT ĐƯỢC CHỮ "CÓ PHÒNG"
        blacklist_kws = [
            'nhượng', 'cho thuê', 'pass', 'có phòng', 'có bạn', 'phòng mình', 
            'ai cần', 'ở ghép', 'chính chủ', 'còn trống', 'mình còn', 'còn phòng', 
            'phòng trống', 'trống 1', 'cho nam thuê', 'cho nữ thuê', 'khai trương',
            'mới tinh', 'giá thuê', 'chỉ từ', 'thiện chí', 'có fix', 
            'nhà mới 100%', 'chỉ còn', 'giảm giá', 'ưu đãi', 
            'miễn phí', 'free'
        ]

        # QUYẾT ĐỊNH ĐIỂM ĐẾN & QUẢN LÝ TAB BẰNG REGISTRY
        if getattr(self, 'tho_san_mode', 'group') == 'newsfeed':
            target_url = "https://www.facebook.com/"
        else:
            group_url = getattr(self, 'current_group_url', "https://www.facebook.com/")
            target_url = group_url

        print(f"      -> Tiến vào khu vực săn bắn: {target_url}")

        if not is_standalone:
            # Mở tab hunt MỚI
            self.driver.switch_to.new_window('tab')
            self._tabs['fb_hunt'] = self.driver.current_window_handle
        else:
            # Standalone: dùng luôn tab hiện tại
            self._tabs['fb_hunt'] = self.driver.current_window_handle
            
        fb_window = self._tabs['fb_hunt']
                mt_window = self._ensure_tab(os.getenv('TARGET_URL', 'https://example-realestate.com'))
        
        # Quay lại tab săn bắn, ép tải URL
        self.driver.switch_to.window(fb_window)
        self.driver.set_page_load_timeout(60)
        time.sleep(1)
        try: self.driver.get(target_url)
        except: pass
        time.sleep(5)

        actions = ActionChains(self.driver)
        
        da_xu_ly_thanh_cong = set() 
        scroll_attempts = 0

        # --- BIẾN THEO DÕI THỜI GIAN VÀ SỐ LƯỢNG KHI ĐI SĂN ---
        start_hunt_time = time.time()
        comment_count = 0
        last_print_time = 0
        
        # ⏱️ THÊM BIẾN CANH GIỜ REFRESH (4 - 5 PHÚT)
        last_refresh_time = time.time()
        refresh_interval = 120
        
        while time.time() < safe_end_time:
            if getattr(self, 'current_credits', 0) < 5:
                print("   🛑 BÁO ĐỘNG: Tài khoản đã hết Token. Bắt buộc thu hồi Thợ Săn về căn cứ!")
                break

            # --- HIỂN THỊ THÔNG TIN THỜI GIAN & SỐ LƯỢNG KHI ĐANG LƯỚT ---
            current_time = time.time()

            # 🔄 CHỈ REFRESH KHI ROBOT ĐANG Ở NGOÀI NEWSFEED (KHÔNG TRONG TAB BÀI VIẾT RIÊNG)
            if current_time - last_refresh_time > refresh_interval:
                # Kiểm tra xem có đang kẹt trong tab phụ nào không để đảm bảo an toàn
                if len(self.driver.window_handles) <= 2:
                    print(f"      🔄 Tiến hành Refresh để giải phóng RAM...")
                    self.driver.switch_to.window(fb_window) # Đảm bảo đang ở tab FB
                    self.driver.refresh()
                    
                    # ĐỢI REFRESH XONG HẲN (Wait for Document Ready)
                    try:
                        WebDriverWait(self.driver, 30).until(
                            lambda d: d.execute_script("return document.readyState") == "complete"
                        )
                        time.sleep(5) # Nghỉ thêm 5s cho UI ổn định
                    except: pass
                    
                    last_refresh_time = time.time()
                    refresh_interval = random.randint(240, 300)

            if current_time - last_print_time > 15: # Cứ 15s in báo cáo 1 lần cho đỡ rác log
                time_left = int(safe_end_time - current_time)
                mins, secs = divmod(time_left, 60)
                print(f"      🕒 Đang đi săn... [Còn lại: {mins:02d} phút {secs:02d} giây] | [Đã bình luận: {comment_count} bài viết!]")
                last_print_time = current_time

            found_new_post = False
            
            for _ in range(random.randint(20, 45)): 
                self.driver.execute_script("window.scrollBy(0, 50);")
                time.sleep(0.25) 
            time.sleep(random.uniform(2, 3)) 

            posts = self.driver.find_elements(By.XPATH, "//div[@role='article' or @aria-posinset]")
            
            for post in posts:
                if time.time() > safe_end_time: break
                try:
                    # ----------------------------------------------------------------
                    # VÒNG 1: GỬI XE (LỌC THÔ BẰNG CODE CŨ - SIÊU TỐC ĐỘ)
                    # ----------------------------------------------------------------
                    raw_text = post.get_attribute('innerText')
                    if not raw_text: raw_text = post.text
                    
                    # TÁCH ĐÔI DỮ LIỆU:
                    # 1. Giữ FULL text (Có tên Group) để Lát nữa dò Khu vực trên Bản đồ
                    post_text = raw_text.lower().strip()
                    
                    # 2. Tạo Body text (Cắt 3 dòng đầu) để Check Môi giới không bị nhầm
                    lines = raw_text.strip().split('\n')
                    # Nếu bài viết dài hơn 3 dòng thì cắt, ngắn quá thì giữ nguyên
                    post_body = '\n'.join(lines[3:]).strip().lower() if len(lines) > 3 else post_text
                    
                    if not post_text or post_text in da_xu_ly_thanh_cong: continue
                    
                    if any(black_kw in post_text for black_kw in blacklist_kws): continue

                    if re.search(r'#\d+([.,]\d+)?\s*(tr|k|m|t|triệu)', post_text):
                        continue
                    
                    # CHECK 1: CHỈ TÌM TỪ KHÓA TÌM PHÒNG BÊN TRONG BODY (Tránh bị lừa bởi Tên Group)
                    is_tim_phong = (
                        any(kw in post_body for kw in [
                            'tìm phòng', 'tìm trọ', 'cần tìm', 'tài chính', 
                            'tìm ccmn', 'mình tìm', 'em tìm', 'mình cần', 
                            'ai có phòng', 'cần thuê', 'đang tìm'
                        ]) 
                        or re.search(r'\btc\b', post_body)
                    )
                    if not is_tim_phong: continue

                    # CHECK 2: RADAR QUÉT MÔI GIỚI CẤP TỐC (Chỉ quét trong Body)
                    broker_patterns = [
                        r'địa chỉ\s*:',           # "Địa chỉ: ngách 142..."
                        r'dạng phòng\s*:',         # "Dạng phòng: đơn kk"
                        r'giá\s*:\s*\d',           # "Giá: 3tr5"
                        r'\d+tr\d*[\s\-–]+phòng',  # "3tr6- Phòng đẹp" hoặc "3tr5 phòng"
                        r'phòng\s+(full|đẹp|mới|sạch|rộng|thoáng)\s+\d',  # "Phòng đẹp 3tr"
                    ]
                    is_broker = any(re.search(p, post_body) for p in broker_patterns)
                    if is_broker:
                        print("      -> 🚫 Bắt quả tang Môi giới/Chủ nhà giả dạng! Bỏ qua ngay.")
                        da_xu_ly_thanh_cong.add(hashlib.md5(post_text.encode('utf-8')).hexdigest())
                        continue

                    # --- NÂNG CẤP: RADAR QUÉT TỪ KHÓA ĐA TẦNG ---
                    found_locs = [] # Khai báo mảng chứa các khu vực vệ tinh
                    for key_group, loc_list in loc_map.items():
                        # Cắt chuỗi 'tmu | đh thương mại' thành mảng ['tmu', 'đh thương mại']
                        keywords = [k.strip() for k in key_group.split('|')]
                        
                        # Nếu bài viết của khách có chứa BẤT KỲ từ nào trong nhóm đó
                        if any(kw in post_text for kw in keywords):
                            found_locs = loc_list # Ôm trọn mảng khu vực vệ tinh (VD: ['Cầu Diễn', 'Hồ Tùng Mậu'])
                            break
                            
                    if not found_locs: continue 
                    
                    found_loc = found_locs[0] # Tạm lấy khu vực ưu tiên số 1 để in ra log hiển thị

                    budget_str = ""
                    price_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(tr|triệu|củ|m(?!\w))', post_text)
                    if price_match:
                        val = float(price_match.group(1).replace(',', '.'))
                        if val < 20: budget_str = str(int(val * 1000000))
                        
                    if not budget_str: continue

                    # Kiểm tra 1: Bài đã xử lý trong RAM chưa?
                    post_hash = hashlib.md5(post_text.encode('utf-8')).hexdigest()
                    if post_hash in da_xu_ly_thanh_cong:
                        continue

                    # Kiểm tra 2: Bài đã được Like chưa? (Tức là đã comment từ phiên trước)
                    like_status = post.find_elements(By.XPATH, ".//div[@aria-label='Gỡ Thích'] | .//div[@aria-label='Thích' and @aria-pressed='true']")
                    if len(like_status) > 0:
                        da_xu_ly_thanh_cong.add(post_hash)  # Ghi vào RAM luôn để lần sau bỏ qua nhanh hơn
                        continue

                    # ----------------------------------------------------------------
                    # VÒNG 2: PHỎNG VẤN (LỌC TINH BẰNG NÃO AI)
                    # ----------------------------------------------------------------
                    # Nếu AI đang trong thời gian phạt (Cooldown) thì bỏ qua gọi API
                    if time.time() < getattr(self, 'ai_cooldown_until', 0):
                        print(f"\n      🧠 Tìm thấy 1 bài tiềm năng ({found_loc} - {budget_str}). [AI ĐANG NGHỈ MỆT], dùng cỗ máy quét tay...")
                        ai_result = None
                    else:
                        print(f"\n      🧠 Tìm thấy 1 bài tiềm năng ({found_loc} - {budget_str}). Đang gửi AI khám xét...")
                        ai_result = self.phan_tich_post_bang_ai(post_text)
                    
                    if ai_result: # Nếu API gọi thành công
                        if not ai_result.get('is_tim_phong', False):
                            print("      -> 🤖 AI bóc phốt: Đây là Môi giới / Chủ nhà lách luật! Quay xe!")
                            da_xu_ly_thanh_cong.add(post_hash)  # THÊM DÒNG NÀY
                            continue
                        
                        # Cập nhật lại thông tin chuẩn xác từ AI
                        if ai_result.get('ngan_sach_max', 0) >= 1500000:
                            budget_str = str(ai_result.get('ngan_sach_max'))
                            
                        # FIX LOGIC SO SÁNH KHU VỰC CHUẨN XÁC
                        ai_loc = ai_result.get('khu_vuc', '').lower()
                        if ai_loc:
                            for key_group, val_list in loc_map.items():
                                kws = [k.strip() for k in key_group.split('|')]
                                # Nếu AI trả về 'cầu giấy' (nằm trong val_list) HOẶC 'sư phạm' (nằm trong kws)
                                if any(kw in ai_loc for kw in kws) or any(v.lower() in ai_loc for v in val_list) or any(ai_loc in v.lower() for v in val_list):
                                    print("     -> AI Trả về: " + val_list[0])
                                    found_loc = val_list[0]
                                    break

                        req_vskk = ai_result.get('vskk', False)
                        req_ban_cong = ai_result.get('ban_cong', False)
                        req_gac_xep = ai_result.get('gac_xep', False)
                        req_xe_dien = ai_result.get('xe_dien', False)
                        req_pet = ai_result.get('nuoi_pet', False)
                    else:
                        # Fallback nếu AI lỗi hoặc đang nghỉ Cooldown
                        req_vskk = any(kw in post_text for kw in ['vskk', 'khép kín', 'vệ sinh riêng', 'vs riêng', 'vệ sinh khép kín'])
                        req_ban_cong = any(kw in post_text for kw in ['ban công', 'ban cong'])
                        req_gac_xep = any(kw in post_text for kw in ['gác xép', 'gác lửng', 'gac xep'])
                        req_xe_dien = any(kw in post_text for kw in ['xe điện', 'sạc'])
                        req_pet = any(kw in post_text for kw in ['pet', 'chó', 'mèo', 'thú cưng'])
                        
                    # --- 3. TÍNH NĂNG MỚI: BỘ LỌC KHÁCH VIP (KÈM LIKE ĐỂ ĐÁNH DẤU) ---
                    if getattr(self, 'hunter_min_budget', 0) > 0 and budget_str:
                        try:
                            # Ép kiểu an toàn để so sánh số nguyên
                            khach_budget = int("".join(filter(str.isdigit, str(budget_str))))
                        except: khach_budget = 0
                            
                        # Nếu tài chính khách NHỎ HƠN mức tối thiểu bạn cấu hình
                        if 0 < khach_budget < self.hunter_min_budget:
                            print(f"      -> 🔻 TỪ CHỐI: Khách tài chính thấp ({khach_budget:,}đ < {self.hunter_min_budget:,}đ).")
                            print("      -> 👍 Đang thả Like ngay ngoài Newsfeed để đánh dấu bỏ qua vĩnh viễn...")
                            try:
                                # Bắn trúng cái nút Like ở bên ngoài Newsfeed mà không cần mở bài viết
                                like_btns = post.find_elements(By.XPATH, ".//div[@aria-label='Thích' and @role='button']")
                                if like_btns:
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", like_btns[0])
                                    time.sleep(0.5)
                                    self.driver.execute_script("arguments[0].click();", like_btns[0])
                                    time.sleep(1)
                            except: pass
                            
                            da_xu_ly_thanh_cong.add(post_hash) # Cất Hash vào sổ đen RAM để chạy mượt hơn
                            continue # Cắt luồng tại đây! Lướt sang bài tiếp theo luôn!
                    # ------------------------------------------------------------------
                    
                    found_new_post = True
                    # Cập nhật lại dòng print để theo dõi trên màn hình Terminal
                    print(f"      👀 Bắt mục tiêu: {found_loc} | Ngân sách: {budget_str} | VSKK: {req_vskk} | Ban công: {req_ban_cong} | Gác: {req_gac_xep} | Pet: {req_pet} | Xe điện: {req_xe_dien}")
                    
                    print("      -> 🎯 Đã khóa mục tiêu! Đang cuộn bài ra giữa màn hình...")
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'smooth'});", post)
                    time.sleep(0.5)
                    self.driver.execute_script("arguments[0].style.outline='1px solid #ffffff'", post)
                    self.driver.execute_script("arguments[0].style.boxShadow='0px 0px 30px #ffffff'", post)
                    self.driver.execute_script("arguments[0].style.transition='all 0.3s'", post)
                    
                    time.sleep(2.5)
                    
                    self.driver.execute_script("arguments[0].style.outline=''", post)
                    self.driver.execute_script("arguments[0].style.boxShadow=''", post)

                    # D. TÌM VÀ CLICK Ô COMMENT
                    print("      -> Đang tìm ô comment trực tiếp trong bài...")
                    post_url = None
                    opened_new_tab = False
                    cmt_window = fb_window

                    time_links = post.find_elements(By.XPATH, ".//a[contains(@href, '/groups/') and (contains(@href, '/posts/') or contains(@href, '/permalink/') or contains(@href, 'multi_permalinks')) and not(contains(@href, '/user/'))]")
                    if time_links: post_url = time_links[0].get_attribute('href')
                    if not post_url:
                        all_links = post.find_elements(By.XPATH, ".//a[@href]")
                        for a in all_links:
                            href = a.get_attribute('href') or ''
                            if ('/posts/' in href or '/permalink/' in href) and '/user/' not in href:
                                post_url = href
                                break

                    if post_url:
                        post_url = post_url.split('?')[0]
                        print(f"      -> Mở tab bài viết: {post_url}")
                        # FIX: Dùng lệnh Native
                        self.driver.switch_to.new_window('tab')
                        cmt_window = self.driver.current_window_handle
                        self.driver.get(post_url)
                        time.sleep(4)
                        dialog_context = self.driver
                        opened_new_tab = True
                    else:
                        wrote_cmt_box = post.find_elements(By.XPATH, ".//div[@aria-label='Viết bình luận' or @aria-label='Write a comment' or @aria-label='Comment' or @aria-label='Bình luận'][@role='button' or @contenteditable]")
                        if wrote_cmt_box:
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", wrote_cmt_box[0])
                            time.sleep(0.5)
                            self.driver.execute_script("arguments[0].click();", wrote_cmt_box[0])
                            time.sleep(2)
                        else:
                            cmt_count_btn = post.find_elements(By.XPATH, ".//div[@role='button'][.//span[contains(text(),'bình luận') or contains(text(),'comment')]]")
                            if cmt_count_btn:
                                self.driver.execute_script("arguments[0].click();", cmt_count_btn[0])
                                time.sleep(2)
                        
                        dialogs = self.driver.find_elements(By.XPATH, "//div[@role='dialog']")
                        dialog_context = dialogs[-1] if dialogs else self.driver
                        opened_new_tab = False

                    # E. LỌC PHÒNG BẰNG TAB CỐ ĐỊNH
                    print("      -> Chuyển sang kho dữ liệu để tìm phòng...")
                    room_data = None
                        
                    # --- 🐞 ĐOẠN CODE DIAGNOSTIC (RADAR QUÉT TAB VÀ BẮT BỆNH) ---
                    try:
                        print("         [DEBUG] --- BẮT ĐẦU KIỂM TRA TÌNH TRẠNG CÁC TAB ---")
                        print(f"         [DEBUG] Hệ thống ghi nhận có {len(self.driver.window_handles)} tab đang mở.")
                        
                        mt_handle_chuan = None
                        for idx, handle in enumerate(self.driver.window_handles):
                            self.driver.switch_to.window(handle)
                            t_url = self.driver.current_url
                            t_title = self.driver.title[:30]
                            print(f"             -> Tab [{idx}]: {t_title} | URL: {t_url}")
                                
                            if "example-realestate.com" in t_url:
                                mt_handle_chuan = handle
                                    
                        if mt_handle_chuan:
                            print("         [DEBUG] ✅ Đã thấy tab! Thực hiện ép Switch...")
                            self.driver.switch_to.window(mt_handle_chuan)
                            mt_window = mt_handle_chuan # Cập nhật lại biến cho chuẩn 100%
                        else:
                            print("         [DEBUG] ❌ KHÔNG THẤY TAB! Đang mở mới bằng Selenium Native...")
                            self.driver.switch_to.new_window('tab') # Lệnh Native
                            mt_window = self.driver.current_window_handle
                            self.driver.get('https://example-realestate.com/listings/')
                            time.sleep(3)
                                
                        print(f"         [DEBUG] Sau khi Switch, Robot thực sự đang ở: {self.driver.current_url}")
                    except Exception as debug_err:
                        print(f"         [DEBUG] ❌ LỖI VĂNG KHI SWITCH TAB: {debug_err}")
                    # --------------------------------------------------------

                    try:
                        # --- FIX MỚI: BỎ ÉP DỪNG TRANG, CHỜ TẢI TỰ NHIÊN ---
                        self.driver.set_page_load_timeout(60) 
                        try:
                            print("         [DEBUG] Đang thực thi lệnh tải lại trang (get)...")
                            self.driver.get('https://example-realestate.com/listings/')
                            print("         [DEBUG] Lệnh tải trang web đã chạy xong!")
                        except TimeoutException:
                            print("         ⚠️ Mạng chậm, trang tải hơi lâu nhưng vẫn tiếp tục...")
                        time.sleep(3)

                        # 1. BẤM XÓA HẾT BỘ LỌC CŨ (CHỐNG DÍNH LỌC CỦA KHÁCH TRƯỚC)
                        try:
                            xoa_het_btns = self.driver.find_elements(By.XPATH, "//*[text()='Xóa hết' or contains(text(), 'Xóa hết')]")
                            for btn in xoa_het_btns:
                                if btn.is_displayed():
                                    self.driver.execute_script("arguments[0].click();", btn)
                                    time.sleep(2)
                                    break
                        except: pass

                        # 2. CHỌN SẮP XẾP: MỚI ĐĂNG TRƯỚC (FIX LỖI KẸT NÚT - CHUẨN XPATH)
                        print("         + Set sắp xếp: Mới đăng trước...")
                        try:
                            sort_boxes = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Sắp xếp theo')]/parent::*//div[contains(@class, 'listivo-select')] | //*[contains(@class, 'listivo-search-results__sort-by')]")
                            if sort_boxes:
                                self.driver.execute_script("arguments[0].click();", sort_boxes[-1])
                                time.sleep(1)
                                    
                                # FIX LỖI "MÙ MÀU": Dùng XPATH tổng quát thay vì ép tìm thẻ <li>
                                sort_new = self.driver.find_elements(By.XPATH, "//*[text()='Mới đăng trước' or contains(text(), 'Mới đăng')]")
                                for el in reversed(sort_new): # Duyệt từ dưới lên để lấy option trong hộp Dropdown vừa mở
                                    if el.is_displayed():
                                        self.driver.execute_script("arguments[0].click();", el)
                                        time.sleep(2)
                                        break
                        except: pass

                        # 3. NHẬP KHU VỰC HOẶC CHỌN BOX QUẬN HUYỆN
                        print(f"         + Đang thiết lập vị trí: {found_loc}...")
                        try:
                            loc_chuyen_sau = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Lọc chuyên sâu') or contains(text(), 'Tìm kiếm nâng cao')]")
                            if loc_chuyen_sau and loc_chuyen_sau[0].is_displayed():
                                self.driver.execute_script("arguments[0].click();", loc_chuyen_sau[0])
                                time.sleep(1.5)
                        except: pass

                        # Check xem location khách muốn có nằm trong danh sách 14 Box Quận/Huyện không
                        danh_sach_quan = ['Hoài Đức', 'Thanh Trì', 'Ba Đình', 'Cầu Giấy', 'Đống Đa', 'Hà Đông', 'Hai Bà Trưng', 'Hoàng Mai', 'Nam Từ Liêm', 'Tây Hồ', 'Thanh Xuân', 'Hoàn Kiếm', 'Long Biên']

                        if found_loc in danh_sach_quan:
                            print("         -> 🎯 Phát hiện từ khóa là Quận/Huyện. Tự động chuyển qua CHỌN BOX...")
                            try:
                                # 1. Bấm mở Box Quận / Huyện
                                quan_box = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'listivo-select-v2__placeholder') and contains(text(), 'Quận / Huyện')]/.. | //*[contains(text(), 'Quận / Huyện')]/parent::*//div[contains(@class, 'listivo-select')]")
                                if quan_box:
                                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", quan_box[-1])
                                    time.sleep(0.5)
                                    self.driver.execute_script("arguments[0].click();", quan_box[-1])
                                    time.sleep(2) # Chờ cái hộp rớt xuống
                                    
                                    # 2. Quét chính xác option có tên Quận để click
                                    quan_opt = self.driver.find_elements(By.XPATH, f"//div[contains(@class, 'listivo-select-v2__dropdown')]//div[contains(text(), '{found_loc}')]")
                                    clicked = False
                                    for opt in reversed(quan_opt): # Duyệt từ dưới lên để lấy option vừa mở
                                        if opt.is_displayed():
                                            self.driver.execute_script("arguments[0].click();", opt)
                                            clicked = True
                                            time.sleep(4) 
                                            break
                                    if not clicked: print("         ⚠️ Không nhấn được option Quận.")
                                else:
                                    print("         ⚠️ Không tìm thấy BOX Quận / Huyện trên web.")
                            except Exception as e:
                                print(f"         ⚠️ Lỗi thao tác chọn Quận: {e}")
                        else:
                            print("         -> ⌨️ Vị trí là đường/trường. Tự động chuyển qua GÕ TỪ KHÓA...")
                            kw_box = WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Từ khóa') or contains(@placeholder, 'Tìm kiếm') or @name='keyword']"))
                            )
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", kw_box)
                            time.sleep(0.5)
                            
                            # FIX KẸT TEXT & CHỐNG CHE KHUẤT
                            try: kw_box.click()
                            except: self.driver.execute_script("arguments[0].focus();", kw_box)
                            
                            kw_box.send_keys(Keys.END)
                            for _ in range(30): kw_box.send_keys(Keys.BACKSPACE)
                            time.sleep(0.5)
                            kw_box.send_keys(found_loc)
                            kw_box.send_keys(Keys.ENTER)
                            time.sleep(4)

                        def check_zero():
                                try:
                                    # Bắt đúng thẻ span chứa con số đếm
                                    count_els = self.driver.find_elements(By.XPATH, "//span[contains(@class, 'listivo-search-results__results-number-count')]")
                                    if len(count_els) > 0 and count_els[0].is_displayed():
                                    # Dùng .strip() để gọt bỏ khoảng trắng (" 0 " -> "0")
                                        if count_els[0].text.strip() == "0": 
                                            return True
                                    return False
                                except: return False    

                        # 4. MỞ KHÓA BỘ LỌC VÀ TÍCH CHỌN TIỆN ÍCH
                        if budget_str or req_vskk or req_ban_cong or req_gac_xep or req_xe_dien or req_pet:                                
                            # A. TÍCH "KHÉP KÍN" ĐỂ UNLOCK FULL OPTION
                            print("         + Đang chọn Loại nhà Khép kín để Mở khóa bộ lọc...")
                            try:
                                khep_kin_opts = self.driver.find_elements(By.XPATH, "//*[text()='Khép kín' or contains(text(), 'Khép kín')]")
                                for el in khep_kin_opts:
                                    if el.is_displayed():
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                                        time.sleep(0.5)
                                        self.driver.execute_script("arguments[0].click();", el)
                                        time.sleep(2) 
                                        break
                            except: pass

                            # B. BẤM NÚT HIỂN THỊ THÊM
                            try:
                                hien_thi = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Hiển thị thêm') or contains(text(), 'Xem thêm')]")
                                for btn in hien_thi:
                                    if btn.is_displayed():
                                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                                        self.driver.execute_script("arguments[0].click();", btn)
                                        time.sleep(1)
                            except: pass
                                
                            # C. TÍCH CÁC TIỆN ÍCH
                            if req_ban_cong:
                                print("         + Đang tích chọn Ban công...")
                                try:
                                    bc_el = self.driver.find_element(By.XPATH, "//div[contains(@class, 'listivo-search-panel__item-label') and contains(normalize-space(), 'Ban công')] | //*[text()='Ban công']")
                                    self.driver.execute_script("arguments[0].click();", bc_el)
                                    time.sleep(1)
                                except: pass
                                    
                            if req_gac_xep:
                                print("         + Đang tích chọn Có gác xép...")
                                try:
                                    gx_el = self.driver.find_element(By.XPATH, "//div[contains(@class, 'listivo-search-panel__item-label') and contains(normalize-space(), 'Có gác xép')] | //*[text()='Có gác xép']")
                                    self.driver.execute_script("arguments[0].click();", gx_el)
                                    time.sleep(1)
                                except: pass

                            if req_pet:
                                print("         + Đang tích chọn Được nuôi pet...")
                                try:
                                    pet_el = self.driver.find_element(By.XPATH, "//div[contains(@class, 'listivo-search-panel__item-label') and contains(normalize-space(), 'Được nuôi pet')] | //*[text()='Được nuôi pet']")
                                    self.driver.execute_script("arguments[0].click();", pet_el)
                                    time.sleep(1)
                                except: pass
                                    
                            if req_xe_dien:
                                print("         + Đang tích chọn Nhận xe điện...")
                                try:
                                    xedien_el = self.driver.find_element(By.XPATH, "//div[contains(@class, 'listivo-search-panel__item-label') and contains(normalize-space(), 'Nhận xe điện')] | //*[text()='Nhận xe điện']")
                                    self.driver.execute_script("arguments[0].click();", xedien_el)
                                    time.sleep(1)
                                except: pass

                            # 5. THUẬT TOÁN NỚI TRẦN NGÂN SÁCH ĐỘC QUYỀN
                            if budget_str:
                                current_budget = int(budget_str)
                                max_budget_limit = current_budget + 3000000 # Nới tối đa 3 triệu
                                
                                den_box = WebDriverWait(self.driver, 5).until(
                                    EC.presence_of_element_located((By.XPATH, "//input[contains(@placeholder, 'Đến...')]"))
                                )
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", den_box)
                                    
                                self.driver.execute_script("arguments[0].value = '';", den_box)
                                time.sleep(random.uniform(1, 1.5))
                                den_box.send_keys(str(current_budget))
                                den_box.send_keys(Keys.ENTER)
                                time.sleep(random.uniform(3, 3.5))

                                # VÒNG LẶP: CHỈ DỪNG KHI THẬT SỰ HẾT SỐ 0
                                while check_zero() and current_budget < max_budget_limit:
                                    print(f"         ⚠️ Hiện tại đang 0 kết quả với giá {current_budget:,}đ. Nới lên 100k nữa...")
                                    current_budget += 300000
                                    den_box = self.driver.find_element(By.XPATH, "//input[contains(@placeholder, 'Đến...')]")
                                    self.driver.execute_script("arguments[0].value = ''; arguments[0].dispatchEvent(new Event('input', { bubbles: true }));", den_box)
                                    time.sleep(random.uniform(1.5, 2))
                                    den_box.send_keys(str(current_budget))
                                    time.sleep(random.uniform(1.2, 1.5))
                                    den_box.send_keys(Keys.ENTER)
                                    self.driver.execute_script("arguments[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', keyCode: 13, bubbles: true }));", den_box)
                                    time.sleep(random.uniform(3.2, 3.7)) # Chờ web xoay load lại

                        # 6. BẮT ĐẦU VÀO LẤY PHÒNG ĐẦU TIÊN
                        has_zero_final = check_zero()
                            
                        # CHẶN BẮT PHÒNG Ở FOOTER: Giới hạn vùng quét chuẩn xác
                        final_cards = []
                        if not has_zero_final:
                            # Chỉ quét bên trong Div chứa danh sách (listivo-search-results__list)
                            final_cards = self.driver.find_elements(By.XPATH, "//div[contains(@class, 'listivo-search-results__list')]//a[contains(@class, 'listivo-listing-card-v4')]")
                                
                            # Fallback nếu không may class vùng quét bị đổi
                            if len(final_cards) == 0:
                                final_cards = self.driver.find_elements(By.CSS_SELECTOR, "a.listivo-listing-card-v4")

                        if len(final_cards) > 0 and not has_zero_final:
                            # --- LƯỚI LỌC SỔ ĐEN CHO THỢ SĂN ---
                            valid_cards = []
                            for card in final_cards:
                                try:
                                    href = card.get_attribute('href')
                                    if href not in getattr(self, 'blacklist_phong', set()):
                                        valid_cards.append(card)
                                except: pass
                                
                            if not valid_cards:
                                print("         🚫 Tất cả phòng tìm được đều nằm trong Sổ Đen! Bỏ qua khách này.")
                                da_xu_ly_thanh_cong.add(post_hash) # Ném vào RAM để vòng sau không lặp lại
                                continue # Cắt luồng tại đây, sang khách tiếp theo
                            
                            # --- THUẬT TOÁN TIỆM CẬN NGÂN SÁCH (TỐI ƯU HOA HỒNG) ---
                            best_link = final_cards[0].get_attribute('href') # Mặc định là căn đầu tiên
                            
                            if budget_str:
                                max_price = -1
                                for card in final_cards[:8]: # Chỉ liếc nhanh 5 thẻ đầu tiên để giữ tốc độ
                                    try:
                                        card_text = card.text.lower()
                                        match = re.search(r'(\d[\d\.]*)\s*đ', card_text) # Bóc tách giá từ text của thẻ
                                        if match:
                                            p_val = int(match.group(1).replace('.', ''))
                                            if p_val > max_price:
                                                max_price = p_val
                                                best_link = card.get_attribute('href')
                                    except: pass
                                
                            # --- FIX MỚI: KIÊN NHẪN CHỜ LOAD XONG ẢNH ---
                            self.driver.set_page_load_timeout(60) 
                            try: self.driver.get(best_link)
                            except TimeoutException: pass
                            
                            print("         + Đang kiên nhẫn chờ web tải xong toàn bộ thông tin và hình ảnh...")
                                
                            # 1. Chờ trạng thái load hoàn toàn tự nhiên (Không dùng window.stop)
                            try:
                                WebDriverWait(self.driver, 45).until(
                                    lambda d: d.execute_script("return document.readyState") == "complete"
                                )
                            except: pass
                            
                            # 2. BẮT BUỘC CHỜ ẢNH HIỆN LÊN MÀN HÌNH MỚI CHO QUA BƯỚC NÀY
                            try:
                                WebDriverWait(self.driver, 45).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, ".listivo-gallery-v2__image"))
                                )
                            except:
                                print("         ⚠️ Đã đợi rất lâu mà ảnh chưa load xong (Có thể mạng rất lag).")
                                    
                            time.sleep(2) # Nghỉ thêm 2s cho UI vẽ mượt
                                
                            # 3. Tiến hành lấy Tiêu đề và giá
                            try:
                                raw_title = WebDriverWait(self.driver, 15).until(
                                    EC.presence_of_element_located((By.CSS_SELECTOR, "h1.listivo-listing-name"))
                                ).text
                            except:
                                raw_title = self.driver.find_element(By.CSS_SELECTOR, "h1.listivo-listing-name").get_attribute('innerText')
                                    
                            price = self.driver.find_element(By.XPATH, "//div[@data-widget_type='lst_listing_price.default']").text
                            short_title = self.format_short_address(raw_title)
                            
                            # --- QUÉT SẠCH THÔNG TIN THỰC TẾ CỦA PHÒNG ---
                            room_features_text = ""
                            try:
                                attr_els = self.driver.find_elements(By.CSS_SELECTOR, ".listivo-listing-attribute-v3, .listivo-listing-feature__text, .listivo-listing-section__text")
                                room_features_text = " ".join([el.text.lower() for el in attr_els])
                            except: pass

                            # --- TÍNH NĂNG MỚI: CHỤP RIÊNG KHUNG ẢNH (CHUẨN ELEMENTOR) ---
                            print("         + Đang chụp mảng ảnh phòng (Element Screenshot)...")
                            temp_path = os.path.abspath("KHO_ANH_HANOI_STAY/temp_hunter_screenshot.png")
                            try:
                                # 1. Bắt chính xác cái KHUNG Elementor dựa trên ảnh F12 của bạn
                                gallery_wrapper = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.XPATH, "//div[@data-widget_type='lst_listing_gallery_v2.default'] | //div[contains(@class, 'elementor-widget-lst_listing_gallery_v2')]"))
                                )

                                # 2. Cuộn cho khung ảnh nằm giữa màn hình để đảm bảo các ảnh con đã được render (Lazy load)
                                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", gallery_wrapper)
                                time.sleep(2) # Đợi mượt mà để các ảnh nhỏ kịp hiện lên

                                # 3. LỆNH THẦN THÁNH: Chỉ chụp đúng cái khung HTML này
                                gallery_wrapper.screenshot(temp_path)

                                room_data = {
                                    "title": short_title,
                                    "price": price,
                                    "img_path": temp_path,
                                    "features_text": room_features_text
                                }
                                print("         -> ✅ Chụp riêng khung ảnh thành công!")
                                    
                            except Exception as e:
                                print(f"         ⚠️ Lỗi tải ảnh trực tiếp ({e}). Bỏ qua ảnh...")
                                room_data = {
                                    "title": short_title, 
                                    "price": price, 
                                    "img_path": "", # Để rỗng để Thợ săn chỉ comment chữ
                                    "features_text": room_features_text
                                }
                                    
                            except Exception as e:
                                print(f"         ⚠️ Lỗi chụp khung ảnh ({e}). Quay về chế độ tải 1 ảnh gốc...")
                                # FALLBACK: Nếu mạng quá lag không thấy khung, quay về tải 1 cái ảnh đơn như cũ
                                gallery = self.driver.find_elements(By.CSS_SELECTOR, ".listivo-gallery-v2__image")
                                if gallery:
                                    res = requests.get(gallery[0].get_attribute('data-url'), timeout=20)
                                    with open(temp_path, 'wb') as f: f.write(res.content)
                                    room_data = {
                                        "title": short_title, 
                                        "price": price, 
                                        "img_path": temp_path, 
                                        "features_text": room_features_text
                                    }
                        else:
                            print("         -> Không có kết quả nào phù hợp kể cả khi đã nới trần.")
                    except Exception as mt_err:
                        print(f"         ❌ Lỗi xử lý: {mt_err}")
                    finally:
                        try:
                            self.driver.switch_to.window(cmt_window)
                        except: pass
                    
                    # F. COMMENT VÀ LIKE BÊN TRONG BÀI VIẾT
                    try:
                        self.driver.switch_to.window(cmt_window)  # THÊM DÒNG NÀY
                    except: pass
                    if room_data:
                        textbox = dialog_context.find_elements(By.XPATH, ".//div[@role='textbox']")
                        if textbox:
                            box = textbox[-1]
                            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", box)
                            time.sleep(1)
                            
                            try:
                                box.click()
                                box.send_keys(Keys.SPACE)
                                box.send_keys(Keys.BACKSPACE)
                            except:
                                self.driver.execute_script("arguments[0].click();", box)
                                box.send_keys(Keys.SPACE)
                                box.send_keys(Keys.BACKSPACE)
                            time.sleep(1)

                            # --- KIỂM TRA CHÉO (CROSS-CHECK) TRƯỚC KHI CHÉM GIÓ ---
                            extra_desc = []
                            rf = room_data.get('features_text', '')
                            
                            if req_vskk and any(kw in rf for kw in ['khép kín', 'studio', 'vệ sinh riêng', 'vs riêng']):
                                extra_desc.append("khép kín")
                                
                            if req_ban_cong and 'ban công' in rf:
                                extra_desc.append("có ban công thoáng")
                                
                            if req_gac_xep and any(kw in rf for kw in ['gác xép', 'gác lửng']):
                                extra_desc.append("có gác xép")

                            if req_pet and any(kw in rf for kw in ['được nuôi pet', 'nhận pet', 'cho nuôi pet']):
                                extra_desc.append("thoải mái nuôi pet")
                                
                            if req_xe_dien and any(kw in rf for kw in ['nhận xe điện', 'sạc xe điện']):
                                extra_desc.append("nhận sạc xe điện")

                            # --- CHUẨN HÓA LẠI GIÁ TIỀN THÀNH DẠNG #4tr HOẶC #4tr5 ---
                            short_price = room_data['price']
                            if 'đ' in short_price.lower():
                                p_num = short_price.lower().replace('đ', '').replace('.', '').replace(',', '').strip()
                                if p_num.isdigit():
                                    val = int(p_num)
                                    if val % 1000000 == 0: short_price = f"#{val // 1000000}tr"
                                    elif val % 100000 == 0: short_price = f"#{val // 1000000}tr{ (val % 1000000) // 100000 }"
                                    else: short_price = f"#{val / 1000000:.1f}tr"
                                else: short_price = f"#{short_price}"
                            else: short_price = f"#{short_price}"

                            extra_str = f" ( Có {', '.join(extra_desc)} ) " if extra_desc else ""
                            
                            c1 = f"{room_data['title']} - Giá chỉ {short_price}{extra_str}. Ưng thì ib {self.user_phone} ( zalo ) mình gửi thêm thông tin"
                            c2 = f"Còn 1 căn {room_data['title']} đang trống{extra_str}, giá chỉ {short_price} ạ. Quan tâm ib Zalo {self.user_phone} mình tư vấn cho nha"
                            c3 = f"{room_data['title']}, giá {short_price}{extra_str}. Ib mình hoặc Zalo {self.user_phone} mình hỗ trợ xem phòng free nha"
                            c4 = f"Mình có sẵn phòng {room_data['title']}{extra_str}, tài chính {short_price}. Bạn nhắn fb chờ hoặc add Zalo {self.user_phone} để mình tư vấn cho nhé"
                            c5 = f"Bạn tham khảo căn {room_data['title']}, giá {short_price}{extra_str}. Ib fb hoặc nhắn zalo {self.user_phone} cho mình nha."
                            c6 = f"Mình có phòng này nha {room_data['title']}. Giá {short_price}{extra_str} nha. Ib hoặc alo Zalo {self.user_phone} đi xem phòng free nhá"

                            cau_chao = random.choice([c1, c2, c3, c4, c5, c6])
                            
                            # Khai báo Chuột/Phím vật lý
                            fresh_actions = ActionChains(self.driver)

                            # 1. ĐÓNG KHUNG CHAT NẾU BỊ CẢN TRỞ
                            try:
                                chat_close_btns = self.driver.find_elements(By.XPATH,
                                    "//div[contains(@aria-label,'Đóng hộp thư') or "
                                    "contains(@aria-label,'Close chat') or "
                                    "contains(@aria-label,'Minimize')][@role='button']"
                                )
                                for btn in chat_close_btns:
                                    if btn.is_displayed():
                                        self.driver.execute_script("arguments[0].click();", btn)
                                        print("      -> 💬 Đã đóng khung chat đang chặn!")
                                        time.sleep(0.5)
                            except: pass

                            # 2. DÁN TEXT (DÙNG CTRL+V ĐƠN GIẢN NHẤT)
                            pyperclip.copy(cau_chao)
                            
                            self.driver.execute_script("arguments[0].focus(); arguments[0].click();", box)
                            time.sleep(0.5)
                            fresh_actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                            time.sleep(1.5)

                            # Kiểm tra xem Facebook đã ăn chữ chưa (Chống kẹt Enter)
                            text_in_box = self.driver.execute_script("return arguments[0].innerText || arguments[0].textContent || '';", box).strip()
                            if not text_in_box:
                                print("      -> ⚠️ FB chưa nhận text, đang thử dán lại...")
                                self.driver.execute_script("arguments[0].focus(); arguments[0].click();", box)
                                time.sleep(0.5)
                                fresh_actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                                time.sleep(1.5)

                            # 3. DÁN ẢNH (CHỈ 1 LẦN DUY NHẤT)
                            if room_data.get('img_path'):
                                ps_paths = f"'{room_data['img_path']}'"
                                subprocess.run(["powershell", "-command", f"Set-Clipboard -Path {ps_paths}"])
                                time.sleep(1.5)
                                
                                self.driver.execute_script("arguments[0].focus(); arguments[0].click();", box)
                                time.sleep(0.5)
                                fresh_actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
                                print("      ⏳ Chờ FB tải ảnh lên (6s)...")
                                time.sleep(6) 

                            # 4. BẤM ENTER ĐỂ GỬI BÀI (1 LẦN DUY NHẤT)
                            self.driver.execute_script("arguments[0].focus();", box)
                            time.sleep(0.5)
                            fresh_actions.send_keys(Keys.ENTER).perform()
                            time.sleep(random.uniform(3.0, 4.0)) # Đợi 3-4s để Facebook kịp phản hồi (Duyệt hoặc Từ chối)

                            # --- LỚP BẢO VỆ MỚI: RADAR PHÁT HIỆN COMMENT BỊ TỪ CHỐI ---
                            bi_tu_choi = False
                            try:
                                # Quét tìm chữ "Bị từ chối" hoặc các cảnh báo spam/vi phạm của FB
                                warning_signs = self.driver.find_elements(By.XPATH, "//*[text()='Bị từ chối' or contains(text(), 'Declined') or contains(text(), 'spam')]")
                                for sign in warning_signs:
                                    if sign.is_displayed():
                                        bi_tu_choi = True
                                        break
                            except: pass

                            if bi_tu_choi:
                                print("      🚫 BÁO ĐỘNG ĐỎ: Facebook vừa TỪ CHỐI comment (Do kiểm duyệt Group hoặc nghi ngờ Spam)!")
                                print("      -> Rút lui khẩn cấp, không ấn Like để bảo toàn tài khoản...")
                                da_xu_ly_thanh_cong.add(post_hash) # Vẫn ghi vào sổ đen RAM để không bao giờ rớ lại bài này
                            else:
                                # Trạng thái an toàn: Chốt đơn thành công, tiến hành Like và đếm số liệu
                                try:
                                    like_btn = dialog_context.find_elements(By.XPATH, ".//div[@aria-label='Thích' and @role='button']")
                                    if like_btn: 
                                        self.driver.execute_script("arguments[0].click();", like_btn[0])
                                        print("      👍 Đã Like đánh dấu bài viết thành công!")
                                except: pass

                                print("      ✅ Tư vấn thành công 1 khách hàng!")
                                da_xu_ly_thanh_cong.add(post_hash) 
                                comment_count += 1 
                                self.thong_ke['hunter'] += 1
                                self.day_log_firebase(status="Active")

                                self.tru_token_firebase(2, "Thợ Săn tư vấn khách")
                                
                        # ---> BẢN VÁ LỖI ẢNH 3: XỬ LÝ KHI BÀI VIẾT BỊ XÓA/KHÓA COMMENT <---
                        else:
                            print("      ⚠️ BÁO ĐỘNG: Không tìm thấy ô Comment! (Trang lỗi, bài đã bị xóa hoặc khóa bình luận).")
                            print("      -> Đã ném bài viết 'ma' này vào sổ đen để phá vỡ vòng lặp vô hạn!")
                            da_xu_ly_thanh_cong.add(post_hash)
                        # ------------------------------------------------------------------
                    else:
                        print("      -> Rất tiếc, kho dữ liệu không có phòng nào khớp yêu cầu này.")
                        # --- TÍNH NĂNG MỚI: LIKE ĐÁNH DẤU CHỐNG VÒNG LẶP VÔ HẠN ---
                        try:
                            like_btn = dialog_context.find_elements(By.XPATH, ".//div[@aria-label='Thích' and @role='button']")
                            if like_btn: 
                                self.driver.execute_script("arguments[0].click();", like_btn[0])
                                print("      👍 Đã Like đánh dấu bài viết (Tránh quét lại)!")
                        except: pass
                        
                        # Vẫn phải thêm vào bộ nhớ RAM để lướt mượt hơn, đỡ phải chờ FB hiển thị nút Like
                        da_xu_ly_thanh_cong.add(post_hash)

                    # G. DỌN DẸP TAB BÀI VIẾT (NẾU CÓ MỞ) ĐỂ LƯỚT TIẾP FB GỐC
                    try:
                        if opened_new_tab:
                            self.driver.close()
                            self.driver.switch_to.window(fb_window)
                            print("      -> Đã đóng tab bài viết riêng, tiếp tục tuần tra...")
                        else:
                            print("      -> Đang dọn dẹp và đóng Popup bài viết...")
                            try:
                                # 1. Bắn ESCAPE trực tiếp vào element đang active (Chuẩn xác 100% như người thật)
                                active_el = self.driver.switch_to.active_element
                                active_el.send_keys(Keys.ESCAPE)
                                time.sleep(1) # Chờ 1s để FB phản ứng (Đóng popup hoặc Hiện cảnh báo)
                                
                                # 2. Kịch bản của bạn: Nếu có text trong ô cmt -> FB hiện bảng cảnh báo
                                is_warning = False
                                dialogs = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Rời khỏi trang') or contains(text(), 'Rời khỏi Trang') or contains(text(), 'Leave')]")
                                for d in dialogs:
                                    if d.is_displayed():
                                        is_warning = True
                                        break
                                        
                                if is_warning:
                                    print("      -> ⚠️ Kẹt cảnh báo, kích hoạt Combo TAB x3 + ENTER của bạn...")
                                    # Phải lấy lại active_element vì hộp thoại Cảnh báo mới nhảy ra đã cướp Focus
                                    alert_el = self.driver.switch_to.active_element
                                    alert_el.send_keys(Keys.TAB)
                                    time.sleep(0.1)
                                    alert_el.send_keys(Keys.TAB)
                                    time.sleep(0.1)
                                    alert_el.send_keys(Keys.TAB)
                                    time.sleep(0.1)
                                    alert_el.send_keys(Keys.ENTER)
                                    time.sleep(1)
                                else:
                                    # 3. Kịch bản Ảnh 2 (Không có phòng): Ô cmt trống, nhưng ESC 1 có thể mới chỉ làm mất Focus ô Like/Cmt.
                                    # Bắn ESC 2 để chắc chắn sập cái Popup bên ngoài.
                                    active_el = self.driver.switch_to.active_element
                                    active_el.send_keys(Keys.ESCAPE)
                                    time.sleep(0.5)
                            except Exception as e_esc:
                                print(f"      ⚠️ Lỗi gửi phím ESC: {e_esc}")

                            # 4. Lưới an toàn cuối cùng: Quét tìm nút (X) ẩn nếu lỡ phím bị kẹt
                            try:
                                close_btns = self.driver.find_elements(By.XPATH, "//div[@role='button' and (contains(@aria-label, 'Đóng') or contains(@aria-label, 'Close'))]")
                                for btn in reversed(close_btns):
                                    if btn.is_displayed():
                                        self.driver.execute_script("arguments[0].click();", btn)
                                        time.sleep(0.5)
                                        break
                            except: pass
                            
                            print("      -> Đã xử lý tắt Popup xong, tiếp tục đi tuần tra...")
                        time.sleep(1.5)
                    except Exception as e_close:
                        print(f"      ⚠️ Lỗi dọn dẹp tab/popup: {e_close}")
                        time.sleep(1.5)

                except Exception as inner_e: 
                    if "stale element" not in str(inner_e).lower():
                        print(f"      ❌ Lỗi ngầm khiến kẹt vòng lặp: {inner_e}")
                finally:
                        # --- BỘ LỌC RÁC CẤP TỐC TẠI CHỖ ---
                        try:
                            current = self.driver.current_window_handle
                            # Nếu tab hiện tại không nằm trong Sổ đăng ký -> Nó là tab rác (Tab bài viết) -> ĐÓNG
                            if current not in (fb_window, mt_window, self._tabs.get('fb_group')):
                                self.driver.close()
                        except: pass
                        
                        # Luôn ép switch về đúng tab săn bắn
                        try:
                            self.driver.switch_to.window(fb_window)
                        except:
                            # Nếu tab săn bắn vô tình bị tắt -> Switch về Group
                            fb_group = self._get_tab('fb_group')
                            if fb_group: self.driver.switch_to.window(fb_group)

            if not found_new_post:
                scroll_attempts += 1
                if scroll_attempts >= 8:
                    if time.time() >= safe_end_time:
                        break
                    scroll_attempts = 0
                    time.sleep(10)
            else:
                scroll_attempts = 0            
        
        total_time_spent = int(time.time() - start_hunt_time)
        t_mins, t_secs = divmod(total_time_spent, 60)
        
        print("\n   " + "🛑"*20)
        print("   BÁO CÁO KẾT THÚC CHUYẾN ĐI SĂN:")
        print(f"   ⏱️ Tổng thời gian lướt: {t_mins:02d} phút {t_secs:02d} giây.")
        print(f"   🎯 Tổng số bài viết đã bình luận: {comment_count} bài.")
        print("   " + "🛑"*20 + "\n")

        if not is_standalone:
            print("   -> Quay lại nhiệm vụ đăng bài Facebook chính!")
            # Đóng tab hunt, giữ tab group + giữ tab
            try:
                hunt_tab = self._tabs.get('fb_hunt')
                if hunt_tab and hunt_tab in self.driver.window_handles:
                    self.driver.switch_to.window(hunt_tab)
                    self.driver.close()
                self._tabs['fb_hunt'] = None
            except: pass
            
            # Dọn sạch mọi tab rác còn sót lại
            self._close_stray_tabs()
            
            # Switch an toàn về Group
            fb_group = self._get_tab('fb_group')
            if fb_group: self.driver.switch_to.window(fb_group)
        else:
            # Standalone kết thúc → dọn rác và xóa registry
            self._close_stray_tabs()
            self._tabs['fb_hunt'] = None
            self._tabs['example'] = None

    def run(self):
        self.get_user_inputs()
        self.init_driver()
        self.login_auto()
        
        # Kiểm tra xem có cần cào dữ liệu list phòng ban đầu không
        # Nếu CHỈ CHẠY duy nhất Thợ Săn Độc Lập (Không up Zalo, Không up FB) thì bỏ qua bước cào
        can_cao_du_lieu = True
        if getattr(self, 'tho_san_doc_lap', False) and not getattr(self, 'dang_zalo', False) and not getattr(self, 'dang_fb', False):
            can_cao_du_lieu = False
            
        if can_cao_du_lieu:
            print("🌍 Đang mở trang danh sách phòng...")
            self.driver.get("https://example-realestate.com/listings/")
            time.sleep(3)
            self.apply_filters()

            print(f"🔍 Đang thu thập {self.num_rooms_to_scrape} link phòng...")
            links = self.get_list_properties(num_rooms=self.num_rooms_to_scrape) 
            print(f"✅ Tổng cộng gom được {len(links)} phòng. Bắt đầu bóc tách dữ liệu...")
            
            for idx, link in enumerate(links): 
                print(f"📦 Đang xử lý [{idx + 1}/{len(links)}]: {link}")
                item_data = self.extract_detail(link)
                self.data.append(item_data)
                time.sleep(random.uniform(1.2, 1.7))

            # self.export_to_excel_custom()
            
        # CHẠY CHIẾN DỊCH THEO YÊU CẦU
        if getattr(self, 'dang_zalo', False):
            self.auto_post_zalo()
            
        if getattr(self, 'dang_fb', False): 
            self.auto_post_facebook()
        elif getattr(self, 'tho_san_doc_lap', False):
            self.run_standalone_hunter()
        
        print("🛑 Chiến dịch hoàn tất. Tự động đóng trình duyệt sau 5 giây...")
        time.sleep(5)
        self.close()

    def export_to_excel_custom(self):
        if not self.data:
            print("❌ Chưa lấy được dữ liệu nào.")
            return
            
        df = pd.DataFrame(self.data)
        now = datetime.now()
        hour_ampm = now.strftime("%I.%M%p").lstrip('0')
        date_str = now.strftime("%d-%m-%y")
        file_name = f"HNSTAY - {hour_ampm} - {date_str}.xlsx"
        
        print(f"🎨 Đang làm đẹp file Excel: {file_name}...")
        with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Data Phong')
            worksheet = writer.sheets['Data Phong']

            custom_font = Font(name='Times New Roman', size=14)
            wrap_alignment = Alignment(wrap_text=True, vertical='top')

            for row in worksheet.iter_rows():
                for cell in row:
                    cell.font = custom_font
                    cell.alignment = wrap_alignment

            column_widths = {'A': 25, 'B': 15, 'C': 30, 'D': 35, 'E': 50, 'F': 65, 'G': 15, 'H': 35}
            for col_letter, width in column_widths.items():
                worksheet.column_dimensions[col_letter].width = width

        print(f"🎉 HOÀN TẤT! File Excel đã được lưu thành công!")

    def close(self):
        if hasattr(self, 'driver'):
            self.driver.quit()
    
    def in_tong_ket(self):
        thoi_gian_chay = int(time.time() - self.tong_thoi_gian_bat_dau)
        gio, du = divmod(thoi_gian_chay, 3600)
        phut, giay = divmod(du, 60)
        
        print("\n" + "🌟"*25)
        print(" "*10 + "BẢNG TỔNG KẾT CHIẾN DỊCH HANOI STAY")
        print("🌟"*25)
        print(f" ⏱️  Tổng thời gian cắm máy : {gio:02d} giờ {phut:02d} phút {giay:02d} giây")
        print(f" 📦  Số phòng đã cào & xử lý: {self.thong_ke['phong_cao']} phòng")
        print(f" 💬  Đăng Zalo thành công   : {self.thong_ke['zalo']} bài")
        print(f" 📘  Đăng FB thành công     : {self.thong_ke['fb']} bài (Bao gồm đăng chéo)")
        print(f" 💣  Rải bom QR Facebook    : {self.thong_ke['qr']} mã")
        print(f" 🎯  Thợ săn chốt khách     : {self.thong_ke['hunter']} bình luận")
        print(f" 💎  Tổng Token đã dùng     : {self.thong_ke.get('token_da_dung', 0):,} Token") # DÒNG MỚI NÀY
        print("🌟"*25)
        print(" "*10 + "🎉 CHÚC BẠN MỘT NGÀY CHỐT SALE BÙNG NỔ! 🎉")
        print("🌟"*25 + "\n")
    
    def phan_tich_post_bang_ai(self, text):
        try:
            # Dùng model flash để phân tích siêu tốc độ
            model = genai.GenerativeModel('gemini-2.5-flash')
            prompt = f"""
                Bạn là chuyên gia phân tích bài viết Facebook phòng trọ Hà Nội.
                Nhiệm vụ: Phân biệt NGƯỜI TÌM PHÒNG (khách hàng) vs CHỦ NHÀ/MÔI GIỚI đang đăng phòng.
                Chỉ trả về DUY NHẤT một chuỗi định dạng JSON (không dùng markdown ```json, không giải thích gì thêm).

                LƯU Ý CỰC KỲ QUAN TRỌNG: 
                - Bài đăng nằm trong Group có tên "Tìm Phòng Trọ..." KHÔNG có nghĩa người đó đang TÌM phòng. Chủ nhà/môi giới cũng đăng vào group này!
                - Dấu hiệu NGƯỜI TÌM: Dùng ngôi thứ nhất ("mình tìm", "em cần"), đưa ra yêu cầu (khu vực, giá), không có địa chỉ ngõ/ngách cụ thể.
                - Dấu hiệu MÔI GIỚI (Cho is_tim_phong = false): Ghi rõ địa chỉ cụ thể ("Ngõ 50 Mễ Trì", "47 Nam Dư"), có cấu trúc liệt kê ("Giá:", "Nội thất:"), kêu gọi hành động ("Ib/zalo", "Lh: 09...").

                Cấu trúc JSON bắt buộc:
                {{
                    "is_tim_phong": true/false,
                    "ngan_sach_max": số nguyên (Ví dụ: khách tìm 4tr5 -> 4500000. Nếu không nói giá hoặc giá không hợp lý, để 0),
                    "khu_vuc": "Tên khu vực khách tìm" (Ví dụ: Cầu Giấy, Cổ Nhuế. Nếu không có để chuỗi rỗng ""),
                    "vskk": true/false (true nếu yêu cầu khép kín),
                    "ban_cong": true/false (true nếu yêu cầu ban công),
                    "gac_xep": true/false (true nếu yêu cầu gác xép),
                    "xe_dien": true/false (true nếu khách dùng xe điện hoặc hỏi chỗ sạc),
                    "nuoi_pet": true/false (true nếu khách có nuôi chó/mèo/thú cưng)
                }}

                Văn bản cần phân tích:
                "{text}"
                """
            response = model.generate_content(prompt)
            # Làm sạch dữ liệu rác (nếu có) để ép kiểu về JSON chuẩn
            raw_json = response.text.strip().replace('```json', '').replace('```', '').strip()
            return json.loads(raw_json)
        except Exception as e:
            error_msg = str(e).lower()
            if '429' in error_msg or 'quota' in error_msg or 'exceeded' in error_msg:
                wait_time = 60 # Mặc định nghỉ 1 phút
                import re
                match = re.search(r'retry in (\d+)', error_msg)
                if match: 
                    wait_time = int(match.group(1)) + 5 # Cộng dư 5s cho an toàn
                
                print(f"      ⛔ AI bị quá tải (Rate Limit)! Tạm khóa bộ não AI trong {wait_time} giây để tránh spam...")
                self.ai_cooldown_until = time.time() + wait_time
            else:
                print(f"      ⚠️ Lỗi gọi API Gemini: {e}")
            return None

# ==============================================================
# BẢNG ĐIỀU KHIỂN LOG MINI (HUD) - ĐÃ FIX MEMORY LEAK
# ==============================================================
class MiniLogger:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("HNStay Live Log")
        
        window_width = 500
        window_height = 350
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - window_width - 20
        y = screen_height - window_height - 60
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self.root.attributes("-topmost", True) 
        self.root.attributes("-alpha", 0.75) 
        self.root.configure(bg='#1e1e1e') 
        
        self.text = tk.Text(self.root, bg='#1e1e1e', fg='#cccccc', font=('Consolas', 10), wrap='word', bd=0, highlightthickness=0)
        self.text.pack(expand=True, fill='both', padx=8, pady=8)
        
        self._log_queue = queue.Queue()
        self.old_stdout = sys.stdout
        sys.stdout = self
        
        # FIX: Dùng Thread riêng để xử lý Queue, không dùng đệ quy after() của Tkinter
        self._running = True
        threading.Thread(target=self._process_queue, daemon=True).start()
        
        # Đảm bảo dọn dẹp khi tắt cửa sổ
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _on_close(self):
        self._running = False
        sys.stdout = self.old_stdout # Trả lại luồng in gốc
        self.root.destroy()
        os._exit(0) # Đóng hẳn toàn bộ app

    def write(self, text):
        if self._running:
            self.old_stdout.write(text)
            self._log_queue.put(text)
        
    def _process_queue(self):
        while self._running:
            try:
                # Đọc Queue với timeout nhỏ để không block thread
                text = self._log_queue.get(timeout=0.1)
                # Chỉ đẩy vào giao diện nếu root còn tồn tại
                if self._running and self.root.winfo_exists():
                    # Gọi an toàn vào luồng chính của Tkinter
                    self.root.after(0, self._insert_text, text)
            except queue.Empty:
                pass
            except Exception:
                pass
        
    def _insert_text(self, text):
        try:
            if self._running and self.text.winfo_exists():
                self.text.insert(tk.END, text)
                self.text.see(tk.END)
                
                # --- ÉP TRẦN ĐÚNG 100 DÒNG ---
                # index(tk.END) trả về định dạng "dòng.cột", ví dụ "105.0"
                total_lines = int(float(self.text.index(tk.END)))
                
                if total_lines > 100:
                    # Tính số dòng thừa và xóa sạch từ đầu (1.0) đến đúng dòng đó
                    lines_to_delete = total_lines - 100
                    self.text.delete("1.0", f"{lines_to_delete}.0")
                    
        except Exception:
            pass
        
    def flush(self):
        self.old_stdout.flush()
        
    def run(self):
        self.root.mainloop()
# ==============================================================
# KHỞI CHẠY CHƯƠNG TRÌNH
# ==============================================================
if __name__ == "__main__":
    SITE_URL = "https://example-realestate.com/" 
    scraper = PropertyAutomationEngine(SITE_URL)
    try:
        # 1. Chạy phần hỏi đáp trong Terminal gốc trước
        scraper.get_user_inputs()
        
        # 2. Khởi tạo Bảng Mini HUD
        gui_logger = MiniLogger()
        
        # 3. GÓI TOÀN BỘ CHỨC NĂNG TOOL VÀO MỘT HÀM CHẠY NGẦM
        def run_tool():
            try:
                scraper.init_driver()
                scraper.login_auto()
                
                can_cao_du_lieu = True
                if getattr(scraper, 'tho_san_doc_lap', False) and not getattr(scraper, 'dang_zalo', False) and not getattr(scraper, 'dang_fb', False):
                    can_cao_du_lieu = False
                    
                if can_cao_du_lieu:
                    print("🌍 Đang mở trang danh sách phòng...")
                    scraper.driver.get("https://example-realestate.com/listings/")
                    time.sleep(3)
                    scraper.apply_filters()

                    print(f"🔍 Đang thu thập {scraper.num_rooms_to_scrape} link phòng...")
                    links = scraper.get_list_properties(num_rooms=scraper.num_rooms_to_scrape) 
                    print(f"✅ Tổng cộng gom được {len(links)} phòng. Bắt đầu bóc tách dữ liệu...")
                    
                    for idx, link in enumerate(links): 
                        print(f"📦 Đang xử lý [{idx + 1}/{len(links)}]: {link}")
                        item_data = scraper.extract_detail(link)
                        scraper.data.append(item_data)
                        scraper.thong_ke['phong_cao'] = len(scraper.data) # Đếm số phòng lấy được
                        time.sleep(1.5)

                    #scraper.export_to_excel_custom()
                    
                if getattr(scraper, 'dang_zalo', False): scraper.auto_post_zalo()
                if getattr(scraper, 'dang_fb', False): scraper.auto_post_facebook()
                elif getattr(scraper, 'tho_san_doc_lap', False): scraper.run_standalone_hunter()
                
                # ---> BỌC BẢNG TỔNG KẾT VÀO CUỐI CÙNG <---
                scraper.in_tong_ket()
                
                print("🛑 Chiến dịch hoàn tất. Tự động đóng trình duyệt sau 5 giây...")
                time.sleep(5)
            except Exception as e:
                print(f"⚠️ Đã xảy ra lỗi hệ thống: {e}")
                # --- BẪY LỖI CRASH VÀ GỬI VỀ CHỈ HUY ---
                error_detail = traceback.format_exc()
                scraper.day_log_firebase(status="Crashed", error_msg=error_detail)
                # ---------------------------------------
            finally:
                scraper.day_log_firebase(status="Completed") # Chốt sổ an toàn
                scraper.close()

        # 4. Bật Tool ở luồng phụ (Chạy nền)
        threading.Thread(target=run_tool, daemon=True).start()
        
        # 5. GIỮ GIAO DIỆN Ở LUỒNG CHÍNH
        gui_logger.run()
    except KeyboardInterrupt:
        # ---> ĐIỂM TIẾP NHẬN PHÍM TẮT CTRL + C KHẨN CẤP <---
        print("\n🛑 Phát hiện tổ hợp phím Ctrl + C! Đang ngắt Robot khẩn cấp...")
        try:
            # Ép đẩy trạng thái Inactive lên chỉ huy ngay lập tức
            scraper.day_log_firebase(status="Inactive", error_msg="User terminated session using Ctrl+C.")
        except: pass
        try:
            scraper.close() # Giải phóng ngay trình duyệt Edge tránh chạy ngầm rác máy
        except: pass
        print("👋 Đã cập nhật trạng thái Inactive lên Firebase và đóng ứng dụng sạch sẽ!")
        os._exit(0) # Tắt triệt để toàn bộ luồng hệ thống