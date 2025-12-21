# Python 程式碼 (公開體驗版 Public Beta) - V1.9
# 修正重點：移除健康總覽卡片內的分隔線

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import uuid
import time 
from PIL import Image, ImageOps 
import io
import base64

# --- 1. 設定頁面 ---
st.set_page_config(page_title="貓咪飲食紀錄 (體驗版)", page_icon="🐱", layout="wide")

# ==========================================
#      設定區
# ==========================================
try:
    SERVICE_ACCOUNT_EMAIL = st.secrets["gcp_service_account"]["client_email"]
except:
    SERVICE_ACCOUNT_EMAIL = "請先設定 Secrets"

# 請確認這裡已換成您的範本連結
TEMPLATE_URL = "https://docs.google.com/spreadsheets/d/1Ou_tXbZGXenP1n5Y_dhj-IzywWEPaWqghVJ8eOx5AQU/edit?usp=sharing"

# --- CSS 注入 ---
def inject_custom_css():
    st.markdown("""
    <style>
        :root { --navy: #012172; --beige: #BBBF95; --bg: #F8FAFC; --text-muted: #5A6B8C; }
        .stApp { background-color: var(--bg); font-family: 'Segoe UI', sans-serif; color: var(--navy); }
        .stMarkdown, .stRadio label, .stNumberInput label, .stSelectbox label, .stTextInput label, p, h1, h2, h3, h4, h5, h6, span, div { color: var(--navy) !important; }
        .stNumberInput input, .stTextInput input, .stSelectbox div[data-baseweb="select"] { color: var(--navy) !important; background-color: #ffffff !important; }
        div[data-testid="stRadio"] label p { color: var(--navy) !important; }
        .block-container { padding-top: 1rem; padding-bottom: 5rem; }
        h4 { font-size: 20px !important; font-weight: 700 !important; color: var(--navy) !important; padding-bottom: 0.5rem; margin-bottom: 0rem; }
        div[data-testid="stVerticalBlock"] > div[style*="background-color"] { background: white; border-radius: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.04); border: 1px solid rgba(1, 33, 114, 0.1); padding: 24px; }
        
        .grid-row-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; }
        .grid-row-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 0px; }
        @media (max-width: 640px) { 
            .grid-row-3 { gap: 6px; } 
            .stat-item { padding: 10px 4px !important; } 
            .stat-value { font-size: 24px !important; } 
            .stat-header { font-size: 12px !important; } 
            div[data-testid="stVerticalBlock"] > div[style*="background-color"] { padding: 16px; } 
        }

        .stat-item { 
            background: #fff; border: 2px solid #e2e8f0; border-radius: 12px; padding: 16px 12px; 
            display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; height: 100%;
        }
        .stat-header { display: flex; align-items: center; justify-content: center; gap: 6px; margin-bottom: 8px; font-size: 14px; font-weight: 700; color: var(--text-muted) !important; text-transform: uppercase; }
        .stat-value { font-size: 32px; font-weight: 900; color: var(--navy) !important; line-height: 1.1; }
        .stat-unit { font-size: 14px; font-weight: 600; color: var(--text-muted) !important; margin-left: 2px; }
        
        .simple-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0; background: #FDFDF9; border: 1px solid var(--beige); border-radius: 12px; padding: 10px 0; margin-bottom: 15px; width: 100%; }
        .simple-item { text-align: center; padding: 0 2px; border-right: 1px solid rgba(1, 33, 114, 0.1); }
        .simple-item:last-child { border-right: none; }
        .simple-label { font-size: 11px; color: var(--text-muted) !important; font-weight: 700; }
        .simple-value { font-size: 16px; color: var(--navy) !important; font-weight: 800; }
        .simple-unit { font-size: 10px; color: var(--text-muted) !important; margin-left: 1px; }
        
        .tag-container { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
        .tag { display: inline-flex; align-items: center; padding: 6px 12px; border-radius: 8px; font-size: 14px; font-weight: 600; border: 1px solid transparent; color: var(--navy) !important; }
        .tag-count { background: rgba(255,255,255,0.8); padding: 0px 6px; border-radius: 4px; font-size: 12px; font-weight: 800; margin-left: 6px; color: var(--navy) !important; }
        
        .bg-orange { background: #fff7ed; color: #f97316; } 
        .bg-blue { background: #eff6ff; color: #3b82f6; } 
        .bg-cyan { background: #ecfeff; color: #06b6d4; } 
        .bg-red { background: #fef2f2; color: #ef4444; } 
        .bg-yellow { background: #fefce8; color: #eab308; }
        .tag-green { background: #ecfdf5; border: 1px solid #d1fae5; color: #047857 !important; } 
        .tag-red { background: #fff1f2; border: 1px solid #ffe4e6; color: #be123c !important; }
        
        .main-header { display: flex; align-items: center; gap: 12px; margin-top: 5px; margin-bottom: 24px; padding: 20px; background: white; border-radius: 16px; border: 1px solid rgba(1, 33, 114, 0.1); box-shadow: 0 4px 6px rgba(0,0,0,0.02); }
        .header-icon { background: var(--navy); padding: 12px; border-radius: 12px; color: white !important; display: flex; }
        
        div[data-testid="stDateInput"] label { font-weight: bold; color: var(--navy); }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
#      工具函式
# ==========================================

def safe_float(value):
    try:
        if value is None: return 0.0
        return float(value)
    except (ValueError, TypeError):
        return 0.0

def get_tw_time():
    tz_tw = timezone(timedelta(hours=8))
    return datetime.now(tz_tw)

def format_time_str(t_str):
    t_str = str(t_str).strip().replace(":", "").replace("：", "")
    if len(t_str) == 3 and t_str.isdigit(): t_str = "0" + t_str
    if len(t_str) == 4 and t_str.isdigit(): return f"{t_str[:2]}:{t_str[2:]}"
    return t_str if ":" in str(t_str) else get_tw_time().strftime("%H:%M")

def clean_duplicate_finish_records(df):
    if df.empty: return df
    mask_finish = df['ItemID'].isin(['WASTE', 'FINISH'])
    df_others = df[~mask_finish]
    df_finish = df[mask_finish]
    if df_finish.empty: return df
    df_finish_clean = df_finish.drop_duplicates(subset=['Meal_Name'], keep='last')
    return pd.concat([df_others, df_finish_clean], ignore_index=True)

def calculate_intake_breakdown(df):
    if df.empty: return 0.0, 0.0
    if 'Category' in df.columns: df['Category'] = df['Category'].astype(str).str.strip()
    exclude_list = ['藥品', '保養品']
    df_calc = df[~df['Category'].isin(exclude_list)].copy()
    if df_calc.empty: return 0.0, 0.0
    df_input = df_calc[df_calc['Net_Quantity'] > 0]
    df_waste = df_calc[df_calc['Net_Quantity'] < 0]
    water_cats = ['水', '飲用水']
    input_water = df_input[df_input['Category'].isin(water_cats)]['Net_Quantity'].sum()
    input_food = df_input[~df_input['Category'].isin(water_cats)]['Net_Quantity'].sum()
    total_input = input_water + input_food
    total_waste = df_waste['Net_Quantity'].sum()
    if total_input > 0:
        ratio_water = input_water / total_input
        ratio_food = input_food / total_input
    else:
        ratio_water = 0.0; ratio_food = 1.0
    final_water_net = input_water + (total_waste * ratio_water)
    final_food_net = input_food + (total_waste * ratio_food)
    return final_food_net, final_water_net

# --- 設定存取與圖片處理工具 ---
def process_image_to_base64(uploaded_file):
    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image) 
        thumb = ImageOps.fit(image, (100, 100), Image.Resampling.LANCZOS)
        buffered = io.BytesIO()
        thumb.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        st.error(f"圖片處理失敗: {e}")
        return None

def get_pet_list(spreadsheet):
    try:
        sh_config = spreadsheet.worksheet("App_Config")
        data = sh_config.get_all_values()
        pets = []
        for row in data:
            if row and row[0].strip():
                img = row[1] if len(row) > 1 else None
                pets.append({"name": row[0], "image": img})
        if not pets: return [{"name": "大文", "image": None}]
        return pets
    except:
        return [{"name": "大文", "image": None}]

def save_pet_to_config(name, image_data, spreadsheet):
    try:
        try:
            sh_config = spreadsheet.worksheet("App_Config")
        except:
            sh_config = spreadsheet.add_worksheet(title="App_Config", rows=20, cols=2)
        
        cell_list = sh_config.col_values(1)
        update_row = len(cell_list) + 1
        if name in cell_list:
            update_row = cell_list.index(name) + 1
            
        sh_config.update_acell(f'A{update_row}', name)
        if image_data:
            sh_config.update_acell(f'B{update_row}', image_data)
            
        st.toast(f"✅ 寵物 {name} 資料已儲存！")
        return True
    except Exception as e:
        st.error(f"設定儲存失敗: {e}")
        return False

# ==========================================
#      HTML 渲染函式
# ==========================================

def render_header(date_str, pet_name, pet_image=None):
    default_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5c.67 0 1.35.09 2 .26 1.78-2 5.03-2.84 6.42-2.26 1.4.58-.42 7-.42 7 .57 1.07 1 2.24 1 3.44C21 17.9 16.97 21 12 21S3 17.9 3 13.44C3 12.24 3.43 11.07 4 10c0 0-1.82-6.42-.42-7 1.39-.58 4.64.26 6.42 2.26.65-.17 1.33-.26 2-.26z"/><path d="M9 13h.01"/><path d="M15 13h.01"/></svg>'
    
    if pet_image:
        icon_html = f'<img src="{pet_image}" style="width:48px; height:48px; border-radius:12px; object-fit:cover;">'
        icon_bg = "transparent"
        icon_padding = "0px"
    else:
        icon_html = default_svg
        icon_bg = "#012172"
        icon_padding = "12px"

    html = f'''
    <div class="main-header">
        <div class="header-icon" style="background:{icon_bg}; padding:{icon_padding}; display:flex; align-items:center; justify-content:center;">
            {icon_html}
        </div>
        <div>
            <div style="font-size:24px; font-weight:800; color:#012172;">{pet_name}的飲食日記</div>
            <div style="font-size:15px; font-weight:500; color:#5A6B8C;">飲食紀錄與趨勢分析</div>
        </div>
    </div>
    '''
    return html

def render_daily_stats_html(day_stats):
    icons = {
        "flame": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.1.2-2.2.6-3.3a1 1 0 0 0 2.1.7z"></path></svg>',
        "utensils": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>',
        "droplets": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 16.3c2.2 0 4-1.83 4-4.05 0-1.16-.57-2.26-1.71-3.19S7.29 6.75 7 5.3c-.29 1.45-1.14 2.84-2.29 3.76S3 11.1 3 12.25c0 2.22 1.8 4.05 4 4.05z"/><path d="M12.56 6.6A10.97 10.97 0 0 0 14 3.02c.5 2.5 2 4.9 4 6.5s3 3.5 3 5.5a6.98 6.98 0 0 1-11.91 4.97"/></svg>',
        "beef": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12.5" cy="8.5" r="2.5"/><path d="M12.5 2a6.5 6.5 0 0 0-6.22 4.6c-1.1 3.13-.78 6.43 1.48 9.17l2.92 2.92c.65.65 1.74.65 2.39 0l.97-.97a6 6 0 0 1 4.24-1.76h.04a6 6 0 0 0 3.79-1.35l.81-.81a2.5 2.5 0 0 0-3.54-3.54l-.47.47a1.5 1.5 0 0 1-2.12 0l-.88-.88a2.5 2.5 0 0 1 0-3.54l.84-.84c.76-.76.88-2 .2-2.86A6.5 6.5 0 0 0 12.5 2Z"/></svg>',
        "dna": '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>'
    }
    
    def get_stat_html(icon, label, value, unit, color_class):
        return f'<div class="stat-item"><div style="margin-bottom:4px;"><div class="stat-header"><div class="stat-icon {color_class}">{icons[icon]}</div>{label}</div></div><div style="display:flex; align-items:baseline; justify-content:center;"><span class="stat-value">{value}</span><span class="stat-unit">{unit}</span></div></div>'
        
    html = '<div class="grid-row-3">'
    html += get_stat_html("flame", "熱量", int(day_stats['cal']), "kcal", "bg-orange")
    html += get_stat_html("utensils", "食物", f"{day_stats['food']:.1f}", "g", "bg-blue")
    html += get_stat_html("droplets", "飲水", f"{day_stats['water']:.1f}", "ml", "bg-cyan")
    html += '</div>'
    
    html += '<div class="grid-row-2">'
    html += get_stat_html("beef", "蛋白質", f"{day_stats['prot']:.1f}", "g", "bg-red")
    html += get_stat_html("dna", "脂肪", f"{day_stats['fat']:.1f}", "g", "bg-yellow")
    html += '</div>'
    return html

def render_supp_med_html(supp_list, med_list):
    def get_tag_html(items, type_class):
        if not items: return '<span style="color:#5A6B8C; font-size:13px;">無</span>'
        tags = ""
        for item in items:
            tags += f'<span class="tag {type_class}">{item["name"]}<span class="tag-count">x{int(item["count"])}</span></span>'
        return tags
    
    html = '<div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px;">'
    html += f'<div><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;font-size:12px;font-weight:700;color:#047857;">🌿 保養品</div><div class="tag-container">{get_tag_html(supp_list, "tag-green")}</div></div>'
    html += f'<div style="border-left:1px solid #f1f5f9;padding-left:20px;"><div><div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;font-size:12px;font-weight:700;color:#be123c;">💊 藥品</div><div class="tag-container">{get_tag_html(med_list, "tag-red")}</div></div></div></div>'
    return html

def render_meal_stats_simple(meal_stats):
    html = '<div class="simple-grid">'
    for l, v, u in [("熱量", int(meal_stats['cal']), "kcal"), ("食物", f"{meal_stats['food']:.1f}", "g"), ("飲水", f"{meal_stats['water']:.1f}", "ml"), ("蛋白", f"{meal_stats['prot']:.1f}", "g"), ("脂肪", f"{meal_stats['fat']:.1f}", "g")]:
        html += f'<div class="simple-item"><div class="simple-label">{l}</div><div class="simple-value">{v}<span class="simple-unit">{u}</span></div></div>'
    return html + '</div>'

# ==========================================
#      連線與登入邏輯
# ==========================================

def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

def load_data_from_url(sheet_url):
    client = init_connection()
    try:
        spreadsheet = client.open_by_url(sheet_url)
        sheet_log = spreadsheet.worksheet("Log_Data")
        sheet_db = spreadsheet.worksheet("DB_Items")
        
        db_data = sheet_db.get_all_records()
        log_data = sheet_log.get_all_records()
        return pd.DataFrame(db_data), pd.DataFrame(log_data), sheet_log, sheet_db, spreadsheet.title, spreadsheet
    except Exception as e:
        return None, None, None, None, str(e), None

if 'user_sheet_url' not in st.session_state: st.session_state.user_sheet_url = None
if 'is_logged_in' not in st.session_state: st.session_state.is_logged_in = False

def login_page():
    inject_custom_css()
    st.title("🐱 貓咪飲食紀錄 - 公開體驗版")
    st.info("👋 歡迎！請依照以下步驟連結您自己的 Google Sheet。")

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            st.markdown("### 步驟 1：建立資料庫")
            st.markdown(f"請建立一份 **範本副本** 到您的 Google Drive，並在 Log_Data 新增 `Pet_Name` 欄位。")
            st.link_button("📄 取得 Google Sheet 範本", TEMPLATE_URL)

    with c2:
        with st.container(border=True):
            st.markdown("### 步驟 2：授權機器人")
            st.markdown("請將您的 Sheet 共用給下方 Email (編輯者)：")
            st.code(SERVICE_ACCOUNT_EMAIL, language="text")

    st.divider()
    url_input = st.text_input("🔗 請貼上您的 Google Sheet 網址：")
    
    if st.button("🚀 連線並開始", type="primary"):
        if not url_input:
            st.error("請輸入網址")
        else:
            with st.spinner("連線測試中..."):
                _items, _log, _sh_log, _sh_db, _msg, _spreadsheet = load_data_from_url(url_input)
                if _items is not None:
                    st.session_state.user_sheet_url = url_input
                    st.session_state.is_logged_in = True
                    st.toast("✅ 連線成功！")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(f"連線失敗：{_msg}")

if not st.session_state.is_logged_in:
    login_page()
    st.stop()

# --- 已登入：讀取資料 ---
df_items, df_log, sheet_log, sheet_db, sheet_title, spreadsheet = load_data_from_url(st.session_state.user_sheet_url)

if df_items is None:
    st.error(f"資料讀取錯誤：{sheet_title}")
    st.session_state.is_logged_in = False
    if st.button("回登入頁"): st.rerun()
    st.stop()

# ==========================================
#      Mapping 初始化
# ==========================================
if not df_items.empty:
    df_items.columns = [c.strip() for c in df_items.columns]
    item_map = dict(zip(df_items['Item_Name'], df_items['ItemID']))
    cal_map = dict(zip(df_items['Item_Name'], df_items['Ref_Cal_100g']))
    prot_map = dict(zip(df_items['Item_Name'], df_items['Protein_Pct']))
    fat_map = dict(zip(df_items['Item_Name'], df_items['Fat_Pct']))
    phos_map = dict(zip(df_items['Item_Name'], df_items['Phos_Pct']))
    cat_map = dict(zip(df_items['Item_Name'], df_items['Category']))
    unit_map = dict(zip(df_items['Item_Name'], df_items['Unit_Type']))
else:
    st.error("讀取不到 DB_Items")
    st.stop()

# ==========================================
#      邏輯函數區
# ==========================================

if 'need_scroll' not in st.session_state: st.session_state.need_scroll = False

def on_cat_change():
    st.session_state.scale_val = None
    st.session_state.need_scroll = True

def on_item_change():
    st.session_state.need_scroll = True

def reset_meal_inputs():
    st.session_state.scale_val = None
    st.session_state.check_zero = False
    st.session_state.waste_gross = None
    st.session_state.waste_tare = None
    st.session_state.finish_radio = "全部吃光 (盤光光)"

def get_previous_meal_density(df_log_data):
    if df_log_data.empty: return None
    try:
        _df = df_log_data.copy()
        _df['Timestamp_dt'] = pd.to_datetime(_df['Timestamp'], errors='coerce')
        # 剩食計算也要過濾寵物
        current_pet = st.session_state.get('selected_pet_name', '')
        if 'Pet_Name' in _df.columns and current_pet:
             _df = _df[_df['Pet_Name'] == current_pet]

        df_waste = _df[_df['ItemID'] == 'WASTE'].copy()
        if df_waste.empty: return None
        
        last_waste = df_waste.sort_values('Timestamp_dt').iloc[-1]
        target_date = last_waste['Date']
        target_meal = last_waste['Meal_Name']
        
        mask_meal = (_df['Date'] == target_date) & (_df['Meal_Name'] == target_meal)
        df_target = _df[mask_meal].copy()
        
        exclude_cats = ['藥品', '保養品']
        exclude_items = ['WASTE', 'FINISH']
        
        for col in ['Net_Quantity', 'Cal_Sub', 'Prot_Sub', 'Fat_Sub', 'Phos_Sub']:
            df_target[col] = pd.to_numeric(df_target[col], errors='coerce').fillna(0)
            
        mask_valid = (
            ~df_target['Category'].isin(exclude_cats) & 
            ~df_target['ItemID'].isin(exclude_items) &
            (df_target['Net_Quantity'] > 0)
        )
        
        df_foods = df_target[mask_valid]
        if df_foods.empty: return None
        
        total_weight = df_foods['Net_Quantity'].sum()
        if total_weight <= 0: return None
        
        density = {
            'cal': df_foods['Cal_Sub'].sum() / total_weight,
            'prot': df_foods['Prot_Sub'].sum() / total_weight,
            'fat': df_foods['Fat_Sub'].sum() / total_weight,
            'phos': df_foods['Phos_Sub'].sum() / total_weight,
            'info': f"依據 {target_date} {target_meal}"
        }
        return density
    except Exception as e:
        return None

def add_to_cart_callback(bowl_w, last_ref_w, last_ref_n):   
    category = st.session_state.get('cat_select', '請選擇...')
    item_name = st.session_state.get('item_select', '請先選類別')
    raw_scale = st.session_state.get('scale_val')
    scale_reading = safe_float(raw_scale)
    is_zeroed = st.session_state.get('check_zero', False)
    
    if category == "請選擇..." or item_name == "請先選類別" or scale_reading <= 0: return

    unit = unit_map.get(item_name, "g")
    net_weight = 0.0
    
    if unit in ["顆", "粒", "錠", "膠囊", "次"]:
        net_weight = scale_reading
        db_scale_reading = last_ref_w  
    else:
        if is_zeroed:
            net_weight = scale_reading
            db_scale_reading = last_ref_w + net_weight 
        else:
            if scale_reading < last_ref_w: return 
            net_weight = scale_reading - last_ref_w
            db_scale_reading = scale_reading

    item_id = item_map.get(item_name, "")
    cat_real = cat_map.get(item_name, "")
    cal_val = safe_float(cal_map.get(item_name, 0))
    prot_val = safe_float(prot_map.get(item_name, 0))
    fat_val = safe_float(fat_map.get(item_name, 0))
    phos_val = safe_float(phos_map.get(item_name, 0))

    if item_id == "LEFTOVER":
        density_data = get_previous_meal_density(df_log)
        if density_data:
            cal_val = density_data['cal'] * 100
            prot_val = density_data['prot'] * 100
            fat_val = density_data['fat'] * 100
            phos_val = density_data['phos'] * 100
            st.toast(f"🔍 已自動代入 {density_data['info']} 的營養密度")
        else:
            st.warning("⚠️ 找不到上一餐的剩餘紀錄，將使用預設數值")

    if unit in ["顆", "粒", "錠", "膠囊", "次"]:
        cal = net_weight * cal_val; prot = net_weight * prot_val; fat = net_weight * fat_val; phos = net_weight * phos_val
    else:
        cal = net_weight * cal_val / 100; prot = net_weight * prot_val / 100; fat = net_weight * fat_val / 100; phos = net_weight * phos_val / 100

    current_meal = st.session_state.meal_selector

    st.session_state.cart.append({
        "Category": cat_real,
        "ItemID": item_id,
        "Item_Name": item_name,
        "Scale_Reading": db_scale_reading,
        "Bowl_Weight": bowl_w,
        "Net_Quantity": net_weight,
        "Cal_Sub": cal,
        "Prot_Sub": prot,
        "Fat_Sub": fat,
        "Phos_Sub": phos,
        "Unit": unit
    })

    st.session_state.scale_val = None
    st.session_state.check_zero = False
    st.session_state.dash_stat_open = False
    st.session_state.dash_med_open = False
    st.session_state.meal_stats_open = False
    st.session_state.meal_selector = current_meal
    st.session_state.just_added = True 

def lock_meal_state():
    if 'meal_selector' in st.session_state: st.session_state.meal_selector = st.session_state.meal_selector

def clear_finish_inputs_callback():
    st.session_state.waste_gross = None
    st.session_state.waste_tare = None

# 寫入時包含 Pet_Name
def save_finish_callback(finish_type, waste_net, waste_cal, bowl_w, meal_n, finish_time_str, finish_date_obj, record_date_obj):
    if finish_type == "有剩餘 (需秤重)" and waste_net <= 0:
        st.session_state.finish_error = "剩餘重量計算錯誤，請檢查輸入數值。"
        return

    str_date_for_db = record_date_obj.strftime("%Y/%m/%d")
    str_finish_date = finish_date_obj.strftime("%Y/%m/%d")
    str_time_finish = f"{finish_time_str}:00"
    timestamp = f"{str_finish_date} {str_time_finish}"
    
    final_waste_net = -waste_net if finish_type == "有剩餘 (需秤重)" else 0
    final_waste_cal = -waste_cal if finish_type == "有剩餘 (需秤重)" else 0
    item_id_code = "WASTE" if finish_type == "有剩餘 (需秤重)" else "FINISH"
    category_code = "剩食" if finish_type == "有剩餘 (需秤重)" else "完食"
    
    current_pet = st.session_state.get('selected_pet_name', '大文')

    row = [
        str(uuid.uuid4()), 
        timestamp,         
        str_date_for_db,   
        str_time_finish,   
        meal_n,
        item_id_code, category_code, 0, bowl_w, 
        final_waste_net, final_waste_cal, 
        0, 0, 0, "",
        "完食紀錄", finish_time_str, 
        current_pet 
    ]
    
    try:
        current_data = sheet_log.get_all_values()
        header = current_data[0]
        try:
            date_idx = header.index('Date')
            meal_idx = header.index('Meal_Name')
            item_idx = header.index('ItemID')
            name_idx = header.index('Item_Name')
            try: pet_idx = header.index('Pet_Name')
            except: pet_idx = -1
        except ValueError:
            date_idx = 2; meal_idx = 4; item_idx = 5; name_idx = 15; pet_idx = -1

        rows_to_delete = []
        for i in range(len(current_data) - 1, 0, -1):
            r = current_data[i]
            is_pet_match = True
            if pet_idx != -1 and len(r) > pet_idx:
                is_pet_match = (r[pet_idx] == current_pet)
            
            if (r[date_idx] == str_date_for_db and 
                r[meal_idx] == meal_n and 
                r[item_idx] in ['WASTE', 'FINISH'] and
                len(r) > name_idx and r[name_idx] == "完食紀錄" and
                is_pet_match):
                rows_to_delete.append(i + 1)
        
        for r_idx in rows_to_delete:
            sheet_log.delete_rows(r_idx)
            
        sheet_log.append_row(row)
        st.toast("✅ 完食紀錄已更新")
        
        st.session_state.meal_selector = meal_n
        clear_finish_inputs_callback()
        st.session_state.just_saved = True
        st.rerun() 
    except Exception as e:
        st.session_state.finish_error = f"寫入失敗：{e}"

# ==========================================
#      UI 佈局開始
# ==========================================
inject_custom_css()

if 'dash_stat_open' not in st.session_state: st.session_state.dash_stat_open = False
if 'dash_med_open' not in st.session_state: st.session_state.dash_med_open = False
if 'meal_stats_open' not in st.session_state: st.session_state.meal_stats_open = False
if 'just_saved' not in st.session_state: st.session_state.just_saved = False
if 'just_added' not in st.session_state: st.session_state.just_added = False
if 'finish_radio' not in st.session_state: st.session_state.finish_radio = "全部吃光 (盤光光)"
if 'nav_mode' not in st.session_state: st.session_state.nav_mode = "➕ 新增食物/藥品"
if 'finish_error' not in st.session_state: st.session_state.finish_error = None

# [V1.4] 讀取寵物列表
pet_list = get_pet_list(spreadsheet)
pet_names = [p['name'] for p in pet_list]

scroll_js = """
<script>
    function smoothScroll() {
        var element = window.parent.document.getElementById("input-anchor");
        if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }
    setTimeout(smoothScroll, 500);
</script>
"""
if st.session_state.just_saved or st.session_state.just_added or st.session_state.get('need_scroll', False):
    components.html(scroll_js, height=0)
    st.session_state.just_saved = False
    st.session_state.just_added = False
    st.session_state.need_scroll = False 

# --- 側邊欄 ---
with st.sidebar:
    st.caption(f"📚 目前連線：{sheet_title}")
    if st.button("登出 / 換資料庫", type="secondary"):
        st.session_state.is_logged_in = False
        st.session_state.user_sheet_url = None
        st.rerun()
    
    st.divider()

    # 寵物切換器
    selected_pet = st.selectbox("🐾 選擇寵物", pet_names, key="selected_pet_name")
    
    # 找到對應的圖片
    current_pet_image = next((p['image'] for p in pet_list if p['name'] == selected_pet), None)

    # 寵物設定 (新增/修改)
    with st.expander("⚙️ 寵物管理"):
        new_name = st.text_input("新增/修改寵物名字", value=selected_pet)
        uploaded_photo = st.file_uploader("上傳大頭照", type=['jpg', 'png', 'jpeg'], help="將自動裁切為正方形")
        
        if st.button("💾 儲存/新增寵物"):
            with st.spinner("處理中..."):
                final_img_str = current_pet_image
                if uploaded_photo:
                    final_img_str = process_image_to_base64(uploaded_photo)
                
                if save_pet_to_config(new_name, final_img_str, spreadsheet):
                    st.rerun()

    st.divider()

    # 編輯日期 (本日)
    st.header("📅 日期與時間") 
    tw_now = get_tw_time()
    record_date = st.date_input("編輯日期", tw_now) 
    str_date_filter = record_date.strftime("%Y/%m/%d")
    
    default_sidebar_time = tw_now.strftime("%H%M")
    raw_record_time = st.text_input("🕒 時間 (如 0618)", value=default_sidebar_time)
    record_time_str = format_time_str(raw_record_time)
    st.caption(f"將記錄為：{record_time_str}")
    
    if st.button("🔄 重新整理數據", type="primary"):
        st.rerun()

# ----------------------------------------------------
# 數據過濾
# ----------------------------------------------------
if 'Pet_Name' in df_log.columns:
    df_pet_log = df_log[df_log['Pet_Name'] == selected_pet].copy()
    if df_pet_log.empty and selected_pet == pet_names[0]: 
         df_pet_log = df_log[ (df_log['Pet_Name'] == selected_pet) | (df_log['Pet_Name'] == "") | (df_log['Pet_Name'].isna()) ].copy()
else:
    df_pet_log = df_log.copy() 

# ----------------------------------------------------
# 4. 佈局實作
# ----------------------------------------------------
date_display = record_date.strftime("%Y年 %m月 %d日")
st.markdown(render_header(date_display, selected_pet, current_pet_image), unsafe_allow_html=True)

col_dash, col_input = st.columns([4, 3], gap="medium")

# --- 左欄：趨勢與總覽 (合併) ---
with col_dash:
    # 健康總覽 (包含趨勢)
    with st.container(border=True):
        st.markdown(f"#### 📊 {date_display} 健康總覽")
        
        # 1. 今日統計
        df_today = pd.DataFrame()
        day_stats = {'cal':0, 'food':0, 'water':0, 'prot':0, 'fat':0}
        supp_list = [] 
        med_list = []
        meal_stats = {'name': '尚未選擇', 'cal':0, 'food':0, 'water':0, 'prot':0, 'fat':0}
        
        if not df_pet_log.empty:
            df_today = df_pet_log[df_pet_log['Date'] == str_date_filter].copy()
            if not df_today.empty:
                if 'Category' in df_today.columns:
                    df_today['Category'] = df_today['Category'].astype(str).str.strip()
                
                for col in ['Cal_Sub', 'Net_Quantity', 'Prot_Sub', 'Fat_Sub']:
                    df_today[col] = pd.to_numeric(df_today[col], errors='coerce').fillna(0)
                
                df_today = clean_duplicate_finish_records(df_today)
                
                day_food_net, day_water_net = calculate_intake_breakdown(df_today)
                day_stats['cal'] = df_today['Cal_Sub'].sum()
                day_stats['food'] = day_food_net
                day_stats['water'] = day_water_net
                day_stats['prot'] = df_today['Prot_Sub'].sum()
                day_stats['fat'] = df_today['Fat_Sub'].sum()

                if 'Category' in df_today.columns:
                    df_supp = df_today[df_today['Category'] == '保養品']
                    if not df_supp.empty:
                        counts = df_supp.groupby('Item_Name')['Net_Quantity'].sum()
                        supp_list = [{'name': k, 'count': v} for k, v in counts.items()]
                    
                    df_med = df_today[df_today['Category'] == '藥品']
                    if not df_med.empty:
                        counts = df_med.groupby('Item_Name')['Net_Quantity'].sum()
                        med_list = [{'name': k, 'count': v} for k, v in counts.items()]

        with st.expander("📝 今日營養攝取", expanded=True): 
             st.markdown(render_daily_stats_html(day_stats), unsafe_allow_html=True)
        with st.expander("💊 今日保養與藥品服用", expanded=st.session_state.dash_med_open):
             st.markdown(render_supp_med_html(supp_list, med_list), unsafe_allow_html=True)

        
        # 2. 趨勢分析
        with st.expander("📈 趨勢分析", expanded=True):
            default_end = get_tw_time().date()
            default_start = default_end - timedelta(days=6)
            
            c_date, c_blank = st.columns([2, 1])
            with c_date:
                date_range = st.date_input("選擇區間", value=(default_start, default_end), max_value=default_end)
            
            if isinstance(date_range, tuple) and len(date_range) == 2:
                start_date, end_date = date_range
            else:
                start_date, end_date = default_start, default_end

            if not df_pet_log.empty:
                temp_dt = pd.to_datetime(df_pet_log['Date'], format='%Y/%m/%d', errors='coerce')
                df_valid = df_pet_log[temp_dt.notna()].copy()
                df_valid['Date_dt'] = temp_dt[temp_dt.notna()].dt.date
                
                mask_range = (df_valid['Date_dt'] >= start_date) & (df_valid['Date_dt'] <= end_date)
                df_trend = df_valid[mask_range].copy()
                
                if not df_trend.empty:
                    for c in ['Cal_Sub', 'Net_Quantity', 'Prot_Sub', 'Fat_Sub']:
                        df_trend[c] = pd.to_numeric(df_trend[c], errors='coerce').fillna(0)
                    
                    df_trend = clean_duplicate_finish_records(df_trend)
                    daily_groups = df_trend.groupby('Date_dt')
                    
                    trend_data = []
                    for d, group in daily_groups:
                        f_net, w_net = calculate_intake_breakdown(group)
                        trend_data.append({
                            'Date': d,
                            '熱量 (kcal)': group['Cal_Sub'].sum(),
                            '食物 (g)': f_net,
                            '飲水 (ml)': w_net
                        })
                    
                    df_chart = pd.DataFrame(trend_data).set_index('Date')
                    
                    tab1, tab2 = st.tabs(["🔥 熱量與食量", "💧 飲水量"])
                    with tab1:
                        st.bar_chart(df_chart[['熱量 (kcal)', '食物 (g)']])
                    with tab2:
                        st.line_chart(df_chart['飲水 (ml)'])
                else:
                    st.info("此區間無資料")
            else:
                st.info("尚無紀錄")

# --- 右欄：操作區 ---
with col_input:
   
    meal_options = ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", 
                    "第六餐", "第七餐", "第八餐", "第九餐", "第十餐", "點心1", "點心2"]

    meal_status_map = {}
    recorded_meals_list = []

    if not df_today.empty:
        recorded_meals_list = df_today['Meal_Name'].unique().tolist()
        for m in recorded_meals_list:
            meal_status_map[m] = " (已記)"
        
        mask_finish = df_today['ItemID'].isin(['FINISH', 'WASTE'])
        df_finished = df_today[mask_finish]

        for _, row in df_finished.iterrows():
            m_name = row['Meal_Name']
            t_str = str(row['Time'])[:5]
            meal_status_map[m_name] = f" (已記) (完食: {t_str})"

    default_meal_name = meal_options[0]
    for m in meal_options:
        if m not in recorded_meals_list:
            default_meal_name = m
            break

    if 'meal_selector' not in st.session_state:
        st.session_state.meal_selector = default_meal_name

    with st.container(border=True):
        st.markdown(f"#### 🍽️ 編輯紀錄 ({selected_pet})")
        
        c_meal, c_bowl = st.columns(2)
        with c_meal:
            def meal_formatter(m):
                suffix = meal_status_map.get(m, "")
                return f"{m}{suffix}"
            
            meal_name = st.selectbox(
                "餐別", 
                meal_options,
                format_func=meal_formatter,
                key="meal_selector",
                on_change=reset_meal_inputs
            )
        
        last_bowl = 30.0
        df_meal = pd.DataFrame()
        if not df_today.empty:
            mask_meal = (df_today['Meal_Name'] == meal_name)
            df_meal = df_today[mask_meal]
            if not df_meal.empty:
                try:
                    last_bowl = float(df_meal.iloc[-1]['Bowl_Weight'])
                except: 
                    pass
        
        with c_bowl:
            bowl_weight = st.number_input("🥣 碗重 (g)", value=last_bowl, step=0.1, format="%.1f")

        if not df_meal.empty:
            with st.expander(f"📜 查看 {meal_name} 已記錄明細"):
                view_df = df_meal[['Item_Name', 'Net_Quantity', 'Cal_Sub', 'Time']].copy()
                def append_time_to_finish(row):
                    if '完食' in str(row['Item_Name']):
                        time_str = str(row['Time'])[:5]
                        return f"{row['Item_Name']} {time_str}"
                    return row['Item_Name']
                view_df['Item_Name'] = view_df.apply(append_time_to_finish, axis=1)
                view_df = view_df.drop(columns=['Time'])
                view_df.columns = ['品名', '數量', '熱量']
                st.dataframe(view_df, use_container_width=True, hide_index=True)

        # 本餐小計
        meal_stats['name'] = meal_name
        if not df_meal.empty:
            for col in ['Cal_Sub', 'Net_Quantity', 'Prot_Sub', 'Fat_Sub']:
                df_meal[col] = pd.to_numeric(df_meal[col], errors='coerce').fillna(0)
            df_meal_clean = clean_duplicate_finish_records(df_meal)
            m_food, m_water = calculate_intake_breakdown(df_meal_clean)
            meal_stats['food'] = m_food
            meal_stats['water'] = m_water
            meal_stats['cal'] = df_meal_clean['Cal_Sub'].sum()
            meal_stats['prot'] = df_meal_clean['Prot_Sub'].sum()
            meal_stats['fat'] = df_meal_clean['Fat_Sub'].sum()
        
        with st.expander("📊 本餐營養小計", expanded=st.session_state.meal_stats_open):
            st.markdown(render_meal_stats_simple(meal_stats), unsafe_allow_html=True)

        st.divider()
        st.markdown('<div id="input-anchor" style="height:0px; margin-top:-10px;"></div>', unsafe_allow_html=True)

        nav_mode = st.radio(
            "操作模式", 
            ["➕ 新增食物/藥品", "🏁 完食/紀錄剩餘"], 
            horizontal=True,
            label_visibility="collapsed",
            key="nav_mode"
        )

        if 'cart' not in st.session_state: st.session_state.cart = []
        
        last_reading_db = bowl_weight
        last_item_db = "碗"
        if not df_meal.empty:
            try:
                df_food_only = df_meal[~df_meal['ItemID'].isin(['WASTE', 'FINISH'])]
                if not df_food_only.empty:
                    last_reading_db = float(df_food_only.iloc[-1]['Scale_Reading'])
                    last_item_db = df_food_only.iloc[-1]['Item_Name']
            except: pass
        
        if len(st.session_state.cart) > 0:
            last_ref_weight = st.session_state.cart[-1]['Scale_Reading']
            last_ref_name = st.session_state.cart[-1]['Item_Name']
        else:
            last_ref_weight = last_reading_db
            last_ref_name = last_item_db

        # --- 模式 1: 新增 ---
        if nav_mode == "➕ 新增食物/藥品":
            st.markdown(f"##### 🍽️ 編輯：{meal_name}")
            
            with st.container(border=True):
                c1, c2 = st.columns(2)
                with c1:
                    unique_cats = ["請選擇..."] + list(df_items['Category'].unique())
                    filter_cat = st.selectbox("1. 類別", unique_cats, key="cat_select", on_change=on_cat_change)
                    
                    filtered_items = []
                    if filter_cat != "請選擇...":
                         filtered_items = df_items[df_items['Category'] == filter_cat]['Item_Name'].tolist()

                with c2:
                    item_name = st.selectbox("2. 品名", filtered_items if filtered_items else ["請先選類別"], key="item_select", on_change=on_item_change)

                unit = unit_map.get(item_name, "g")
                
                c3, c4 = st.columns(2)
                with c3:
                    if 'scale_val' not in st.session_state: st.session_state.scale_val = None
                    
                    if unit in ["顆", "粒", "錠", "膠囊", "次"]:
                        scale_reading_ui = st.number_input(f"3. 數量 ({unit})", step=1.0, key="scale_val", value=None, placeholder="輸入數量")
                        is_zeroed_ui = True 
                    else:
                        scale_reading_ui = st.number_input("3. 秤重讀數 (g)", step=0.1, format="%.1f", key="scale_val", value=None, placeholder="輸入重量")
                        st.caption(f"前筆: {last_ref_weight} g ({last_ref_name})")
                        is_zeroed_ui = st.checkbox("⚖️ 已歸零 / 單獨秤重", value=False, key="check_zero")

                with c4:
                    net_weight_disp = 0.0
                    calc_msg_disp = "請輸入"
                    scale_val = safe_float(scale_reading_ui)
                    
                    if scale_val > 0:
                        if unit in ["顆", "粒", "錠", "膠囊", "次"]:
                            net_weight_disp = scale_val
                            calc_msg_disp = f"單位: {unit}"
                        else:
                            if is_zeroed_ui:
                                net_weight_disp = scale_val
                                calc_msg_disp = "單獨秤重"
                            else:
                                if scale_val < last_ref_weight:
                                    calc_msg_disp = "⚠️ 數值異常"
                                    net_weight_disp = 0.0
                                else:
                                    net_weight_disp = scale_val - last_ref_weight
                                    calc_msg_disp = f"扣除前筆 {last_ref_weight}"
                    
                    if "異常" in calc_msg_disp:
                        st.metric("淨重", "---", delta=calc_msg_disp, delta_color="inverse")
                    else:
                        st.metric("淨重", f"{net_weight_disp:.1f}", delta=calc_msg_disp, delta_color="off")

                btn_disabled = False
                if filter_cat == "請選擇..." or item_name == "請先選類別": btn_disabled = True
                if scale_val <= 0: btn_disabled = True
                if "異常" in calc_msg_disp: btn_disabled = True 

                st.button("⬇️ 加入清單", 
                          type="secondary", 
                          use_container_width=True, 
                          disabled=btn_disabled,
                          on_click=add_to_cart_callback,
                          args=(bowl_weight, last_ref_weight, last_ref_name)
                )

            if st.session_state.cart:
                st.markdown("---")
                st.markdown("##### 🛒 待存清單 (可編輯)")
                df_cart = pd.DataFrame(st.session_state.cart)
                
                edited_df = st.data_editor(
                    df_cart,
                    use_container_width=True,
                    column_config={
                        "Item_Name": "品名",
                        "Net_Quantity": st.column_config.NumberColumn("數量/淨重", format="%.1f"),
                        "Cal_Sub": st.column_config.NumberColumn("熱量", format="%.1f")
                    },
                    column_order=["Item_Name", "Net_Quantity", "Cal_Sub"],
                    num_rows="fixed", 
                    key="cart_editor"
                )
                
                edited_df = edited_df.dropna(subset=['Item_Name'])
                edited_df = edited_df[edited_df['Item_Name'] != ""]

                if not edited_df.empty:
                    try:
                        edited_df['Net_Quantity'] = pd.to_numeric(edited_df['Net_Quantity'], errors='coerce').fillna(0)
                        edited_df['Cal_Sub'] = pd.to_numeric(edited_df['Cal_Sub'], errors='coerce').fillna(0)
                        
                        if 'Category' in edited_df.columns:
                            mask_food = ~edited_df['Category'].isin(['藥品', '保養品'])
                            live_sum_net = edited_df.loc[mask_food, 'Net_Quantity'].sum()
                        else:
                            live_sum_net = edited_df['Net_Quantity'].sum()
                            
                        live_sum_cal = edited_df['Cal_Sub'].sum()
                        st.info(f"∑ 總計 (不含藥)：{live_sum_net:.1f} g  |  🔥 {live_sum_cal:.1f} kcal")
                    except: pass

                delete_options = ["請選擇要刪除的項目..."] + [f"{i+1}. {row['Item_Name']} ({row['Net_Quantity']}g)" for i, row in edited_df.iterrows()]
                del_item = st.selectbox("🗑️ 刪除項目 (行動版專用)", delete_options)
                
                if del_item != "請選擇要刪除的項目..." and st.button("確認刪除", type="secondary"):
                    try:
                        idx_to_del = int(del_item.split(".")[0]) - 1
                        if 0 <= idx_to_del < len(st.session_state.cart):
                            st.session_state.cart.pop(idx_to_del)
                            st.rerun()
                    except:
                        st.error("刪除失敗，請重新整理頁面")

                if st.button("💾 儲存寫入 Google Sheet", type="primary", use_container_width=True, on_click=lock_meal_state):
                    if edited_df.empty:
                        st.warning("清單為空或資料不完整")
                    else:
                        with st.spinner("寫入中..."):
                            rows = []
                            str_date = record_date.strftime("%Y/%m/%d")
                            str_time = f"{record_time_str}:00"
                            timestamp = f"{str_date} {str_time}"
                            
                            current_pet = st.session_state.get('selected_pet_name', '大文')

                            for i, row_data in edited_df.iterrows():
                                orig_item = next((x for x in st.session_state.cart if x['Item_Name'] == row_data['Item_Name']), {})
                                safe_net = safe_float(row_data['Net_Quantity'])
                                safe_cal = safe_float(row_data['Cal_Sub'])

                                row = [
                                    str(uuid.uuid4()), timestamp, str_date, str_time, meal_name,
                                    orig_item.get('ItemID', ''), orig_item.get('Category', ''), 
                                    orig_item.get('Scale_Reading', 0), orig_item.get('Bowl_Weight', 0), 
                                    safe_net, safe_cal,
                                    orig_item.get('Prot_Sub', 0), orig_item.get('Fat_Sub', 0), 
                                    orig_item.get('Phos_Sub', 0), "", row_data['Item_Name'], "",
                                    current_pet
                                ]
                                rows.append(row)
                            try:
                                sheet_log.append_rows(rows)
                                st.toast("✅ 寫入成功！")
                                st.session_state.cart = []
                                st.session_state.dash_stat_open = False
                                st.session_state.dash_med_open = False
                                st.session_state.meal_stats_open = False
                                # [修正] 用 rerun 代替 load_data.clear()
                                st.session_state.just_saved = True 
                                st.rerun()
                            except Exception as e:
                                st.error(f"寫入失敗：{e}")

        # --- 模式 2: 完食 ---
        elif nav_mode == "🏁 完食/紀錄剩餘":
            st.markdown(f"##### 🍽️ 編輯：{meal_name}")
            st.caption("紀錄完食時間，若有剩餘，請將剩食倒入新容器(或原碗)秤重")
            
            finish_date = st.date_input("完食日期 (跨日請選實際日期)", value=record_date, key="finish_date_picker")
            default_now = get_tw_time().strftime("%H%M")
            raw_finish_time = st.text_input("完食時間 (如 0200)", value=default_now, key="finish_time_input")
            fmt_finish_time = format_time_str(raw_finish_time)
            
            if finish_date != record_date:
                st.info(f"💡 此紀錄將歸屬在 **{record_date.strftime('%m/%d')}** 的 {meal_name}，但時間標記為 **{finish_date.strftime('%m/%d')} {fmt_finish_time}**")
            else:
                st.caption(f"📝 將記錄為：{fmt_finish_time}")

            finish_type = st.radio("狀態", ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], horizontal=True, key="finish_radio")
            waste_net = 0.0
            waste_cal = 0.0
            
            if finish_type == "有剩餘 (需秤重)":
                st.markdown("---")
                c_w1, c_w2 = st.columns(2)
                with c_w1:
                    waste_gross = st.number_input("1. 容器+剩食 總重 (g)", min_value=0.0, step=0.1, key="waste_gross", value=None, placeholder="輸入總重")
                with c_w2:
                    waste_tare = st.number_input("2. 容器空重 (g)", min_value=0.0, step=0.1, key="waste_tare", value=None, placeholder="輸入空重")
                val_gross = safe_float(waste_gross)
                val_tare = safe_float(waste_tare)
                waste_net = val_gross - val_tare
                
                if waste_gross is not None and waste_tare is not None:
                    if waste_net > 0:
                        st.warning(f"📉 實際剩餘淨重：{waste_net:.1f} g")
                        if not df_meal.empty:
                            df_meal_clean = clean_duplicate_finish_records(df_meal)
                            meal_foods = df_meal_clean[df_meal_clean['Net_Quantity'].apply(lambda x: safe_float(x)) > 0]
                            exclude_meds = ['藥品', '保養品']
                            if 'Category' in meal_foods.columns:
                                meal_foods['Category'] = meal_foods['Category'].astype(str).str.strip()
                                calc_df = meal_foods[~meal_foods['Category'].isin(exclude_meds)]
                                total_in_cal = calc_df['Cal_Sub'].apply(safe_float).sum()
                                total_in_weight = calc_df['Net_Quantity'].apply(safe_float).sum()
                                if total_in_weight > 0:
                                    avg_density = total_in_cal / total_in_weight
                                    waste_cal = waste_net * avg_density
                                    st.caption(f"預估扣除熱量：{waste_cal:.1f} kcal")
                    elif val_gross > 0 and waste_net <= 0:
                        st.error("空重不能大於總重！")

            st.button("💾 記錄完食/剩餘", type="primary", on_click=save_finish_callback, args=(finish_type, waste_net, waste_cal, bowl_weight, meal_name, fmt_finish_time, finish_date, record_date))