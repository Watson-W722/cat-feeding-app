# Python 程式碼 V12.4 (2026 Pro Edition)
# 1. 補回 Dashboard 完整指標圖示與顏色區塊
# 2. 補回餐點明細表格 (含完食時間拼接)
# 3. 解決購物車刪除需點兩次的問題
# 4. 全面符合 2026 Streamlit 規範 (width="stretch")

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import uuid

# 視覺化套件
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# --- 1. 設定頁面 ---
st.set_page_config(page_title="大文的飲食日記", page_icon="🐱", layout="wide")

# --- 小工具 ---
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
    if len(t_str) == 3 and t_str.isdigit():
        t_str = "0" + t_str
    if len(t_str) == 4 and t_str.isdigit():
        return f"{t_str[:2]}:{t_str[2:]}"
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
    ratio_water = input_water / total_input if total_input > 0 else 0.0
    ratio_food = input_food / total_input if total_input > 0 else 1.0
    return input_food + (total_waste * ratio_food), input_water + (total_waste * ratio_water)

# --- CSS 注入 ---
def inject_custom_css():
    st.markdown("""
    <style>
        :root { --navy: #012172; --beige: #BBBF95; --bg: #F8FAFC; --text-muted: #5A6B8C; }
        .stApp { background-color: var(--bg); font-family: 'Segoe UI', sans-serif; color: var(--navy); }
        .stMarkdown, .stRadio label, .stNumberInput label, .stSelectbox label, .stTextInput label, p, h1, h2, h3, h4, h5, h6, span, div { color: var(--navy) !important; }
        div[data-testid="stVerticalBlock"] > div[style*="background-color"] { background: white; border-radius: 16px; border: 1px solid rgba(1,33,114,0.1); padding: 24px; }
        /* Dashboard 指標樣式 */
        .stat-item { background: #fff; border: 2px solid #e2e8f0; border-radius: 12px; padding: 16px 12px; display: flex; flex-direction: column; align-items: center; text-align: center; }
        .stat-header { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 14px; font-weight: 700; color: var(--text-muted) !important; text-transform: uppercase; }
        .stat-value { font-size: 30px; font-weight: 900; color: var(--navy) !important; line-height: 1.1; }
        .stat-unit { font-size: 14px; font-weight: 600; color: var(--text-muted) !important; margin-left: 2px; }
        .grid-row-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; }
        .grid-row-2 { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 0px; }
        .bg-orange { background: #fff7ed; color: #f97316; padding: 4px; border-radius: 6px; }
        .bg-blue { background: #eff6ff; color: #3b82f6; padding: 4px; border-radius: 6px; }
        .bg-cyan { background: #ecfeff; color: #06b6d4; padding: 4px; border-radius: 6px; }
        .bg-red { background: #fef2f2; color: #ef4444; padding: 4px; border-radius: 6px; }
        .bg-yellow { background: #fefce8; color: #eab308; padding: 4px; border-radius: 6px; }
        /* Tag 樣式 */
        .tag-container { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
        .tag { display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 8px; font-size: 13px; font-weight: 600; }
        .tag-green { background: #ecfdf5; border: 1px solid #d1fae5; color: #047857 !important; }
        .tag-red { background: #fff1f2; border: 1px solid #ffe4e6; color: #be123c !important; }
        .tag-count { background: rgba(255,255,255,0.8); padding: 0px 4px; border-radius: 4px; margin-left: 4px; }
        /* 小計 Grid */
        .simple-grid { display: grid; grid-template-columns: repeat(5, 1fr); background: #FDFDF9; border: 1px solid var(--beige); border-radius: 12px; padding: 10px 0; margin-bottom: 15px; width: 100%; }
        .simple-item { text-align: center; border-right: 1px solid rgba(1, 33, 114, 0.1); }
        .simple-item:last-child { border-right: none; }
        .main-header { display: flex; align-items: center; gap: 12px; margin-top: 5px; margin-bottom: 24px; padding: 20px; background: white; border-radius: 16px; border: 1px solid rgba(1, 33, 114, 0.1); }
        .header-icon { background: var(--navy); padding: 12px; border-radius: 12px; color: white !important; display: flex; }
    </style>
    """, unsafe_allow_html=True)

def render_header(date_str):
    cat_svg = '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5c.67 0 1.35.09 2 .26 1.78-2 5.03-2.84 6.42-2.26 1.4.58-.42 7-.42 7 .57 1.07 1 2.24 1 3.44C21 17.9 16.97 21 12 21S3 17.9 3 13.44C3 12.24 3.43 11.07 4 10c0 0-1.82-6.42-.42-7 1.39-.58 4.64.26 6.42 2.26.65-.17 1.33-.26 2-.26z"/></svg>'
    return f'<div class="main-header"><div class="header-icon">{cat_svg}</div><div><div style="font-size:24px; font-weight:800; color:#012172;">大文的飲食日記</div><div style="font-size:15px; font-weight:500; color:#5A6B8C;">{date_str}</div></div></div>'

def render_daily_stats_html(day_stats):
    def get_stat_html(label, value, unit, color_class):
        return f'<div class="stat-item"><div class="stat-header {color_class}">{label}</div><div style="display:flex; align-items:baseline;"><span class="stat-value">{value}</span><span class="stat-unit">{unit}</span></div></div>'
    html = '<div class="grid-row-3">' + get_stat_html("熱量", int(day_stats['cal']), "kcal", "bg-orange") + get_stat_html("食物", f"{day_stats['food']:.1f}", "g", "bg-blue") + get_stat_html("飲水", f"{day_stats['water']:.1f}", "ml", "bg-cyan") + '</div>'
    html += '<div class="grid-row-2">' + get_stat_html("蛋白質", f"{day_stats['prot']:.1f}", "g", "bg-red") + get_stat_html("脂肪", f"{day_stats['fat']:.1f}", "g", "bg-yellow") + '</div>'
    return html

def render_supp_med_html(supp_list, med_list):
    def get_tag_html(items, type_class):
        if not items: return '<span style="color:#5A6B8C; font-size:13px;">無</span>'
        return "".join([f'<span class="tag {type_class}">{item["name"]}<span class="tag-count">x{int(item["count"])}</span></span>' for item in items])
    html = '<div style="display:grid; grid-template-columns: 1fr 1fr; gap:20px; margin-top:10px;">'
    html += f'<div><div style="font-size:12px;font-weight:700;color:#047857;margin-bottom:4px;">保養品</div><div class="tag-container">{get_tag_html(supp_list, "tag-green")}</div></div>'
    html += f'<div style="border-left:1px solid #f1f5f9;padding-left:20px;"><div><div style="font-size:12px;font-weight:700;color:#be123c;margin-bottom:4px;">藥品</div><div class="tag-container">{get_tag_html(med_list, "tag-red")}</div></div></div></div>'
    return html

def render_meal_stats_simple(meal_stats):
    html = '<div class="simple-grid">'
    for l, v, u in [("熱量", int(meal_stats['cal']), "kcal"), ("食物", f"{meal_stats['food']:.1f}", "g"), ("飲水", f"{meal_stats['water']:.1f}", "ml"), ("蛋白", f"{meal_stats['prot']:.1f}", "g"), ("脂肪", f"{meal_stats['fat']:.1f}", "g")]:
        html += f'<div class="simple-item"><div style="font-size:11px; color:#5A6B8C;">{l}</div><div style="font-size:16px; font-weight:800;">{v}<span style="font-size:10px;">{u}</span></div></div>'
    return html + '</div>'

# --- 連線與資料讀取 ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    client = gspread.authorize(creds)
    return client

try:
    client = init_connection()
    spreadsheet = client.open("DaWen daily record")
    sheet_log = spreadsheet.worksheet("Log_Data")
    sheet_db = spreadsheet.worksheet("DB_Items")
except Exception as e:
    st.error(f"連線失敗：{e}"); st.stop()

@st.cache_data(ttl=5)
def load_data():
    return pd.DataFrame(sheet_db.get_all_records()), pd.DataFrame(sheet_log.get_all_records())

df_items, df_log = load_data()
if not df_items.empty:
    df_items.columns = [c.strip() for c in df_items.columns]
    item_map = dict(zip(df_items['Item_Name'], df_items['ItemID']))
    cal_map = dict(zip(df_items['Item_Name'], df_items['Ref_Cal_100g']))
    prot_map = dict(zip(df_items['Item_Name'], df_items['Protein_Pct']))
    fat_map = dict(zip(df_items['Item_Name'], df_items['Fat_Pct']))
    phos_map = dict(zip(df_items['Item_Name'], df_items['Phos_Pct']))
    cat_map = dict(zip(df_items['Item_Name'], df_items['Category']))
    unit_map = dict(zip(df_items['Item_Name'], df_items['Unit_Type']))

# --- 核心邏輯函數 ---
def add_to_cart_callback(bowl_w, last_ref_w, last_ref_n):   
    category, item_name = st.session_state.get('cat_select'), st.session_state.get('item_select')
    sc_reading = safe_float(st.session_state.get('scale_val'))
    is_zeroed = st.session_state.get('check_zero', False)
    if category == "請選擇..." or sc_reading <= 0: return
    unit = unit_map.get(item_name, "g")
    
    if unit in ["g", "ml"]:
        if is_zeroed: net_q, db_sc = sc_reading, last_ref_w + sc_reading
        else: net_q, db_sc = sc_reading - last_ref_w, sc_reading
    else: net_q, db_sc = sc_reading, last_ref_w

    cal_v, prot_v, fat_v, phos_v = safe_float(cal_map.get(item_name)), safe_float(prot_map.get(item_name)), safe_float(fat_map.get(item_name)), safe_float(phos_map.get(item_name))
    mult = 1 if unit not in ["g", "ml"] else (net_q / 100)
    st.session_state.cart.append({
        "Category": cat_map.get(item_name), "ItemID": item_map.get(item_name), "Item_Name": item_name,
        "Scale_Reading": db_sc, "Bowl_Weight": bowl_w, "Net_Quantity": net_q,
        "Cal_Sub": cal_v*mult, "Prot_Sub": prot_v*mult, "Fat_Sub": fat_v*mult, "Phos_Sub": phos_v*mult, "Unit": unit
    })
    st.session_state.scale_val, st.session_state.check_zero = None, False
    st.session_state.just_added = True

def save_finish_callback(f_type, w_net, w_cal, bowl_w, meal_n, f_time, f_date, rec_date):
    if f_type == "有剩餘 (需秤重)" and w_net <= 0: return
    s_db_d, s_f_d = rec_date.strftime("%Y/%m/%d"), f_date.strftime("%Y/%m/%d")
    row = [str(uuid.uuid4()), f"{s_f_d} {f_time}:00", s_db_d, f"{f_time}:00", meal_n, "WASTE" if "剩" in f_type else "FINISH", "剩食" if "剩" in f_type else "完食", 0, bowl_w, -w_net if "剩" in f_type else 0, -w_cal if "剩" in f_type else 0, 0, 0, 0, "", "完食紀錄", f_time]
    try:
        curr = sheet_log.get_all_values()
        h = curr[0]
        d_i, m_i, it_i, n_i = h.index('Date'), h.index('Meal_Name'), h.index('ItemID'), h.index('Item_Name')
        for i in sorted([idx for idx, r in enumerate(curr[1:], 1) if r[d_i]==s_db_d and r[m_i]==meal_n and r[it_i] in ['WASTE', 'FINISH'] and r[n_i]=="完食紀錄"], reverse=True): sheet_log.delete_rows(i+1)
        sheet_log.append_row(row)
        st.toast("✅ 完食紀錄已更新"); load_data.clear(); st.session_state.just_saved = True; st.rerun()
    except Exception as e: st.error(f"寫入失敗：{e}")

# --- UI 佈局 ---
inject_custom_css()
if 'cart' not in st.session_state: st.session_state.cart = []
for k in ['dash_stat_open', 'dash_med_open', 'meal_stats_open', 'just_saved', 'just_added', 'need_scroll']:
    if k not in st.session_state: st.session_state[k] = False

# 捲動 JS
scroll_js = """<script>function smoothScroll(){var e=window.parent.document.getElementById("input-anchor");if(e)e.scrollIntoView({behavior:'smooth',block:'start'})}setTimeout(smoothScroll,500);</script>"""
if st.session_state.just_saved or st.session_state.just_added or st.session_state.need_scroll:
    components.html(scroll_js, height=0); st.session_state.just_saved = st.session_state.just_added = st.session_state.need_scroll = False

with st.sidebar:
    st.header("⚙️ 設定")
    tw_now = get_tw_time()
    rec_date = st.date_input("📅 日期", tw_now)
    rec_time_str = format_time_str(st.text_input("🕒 時間", value=tw_now.strftime("%H%M")))
    if st.button("🔄 重新整理"): load_data.clear(); st.rerun()

# --- Dashboard 數據處理 ---
df_today = df_log[df_log['Date'] == rec_date.strftime("%Y/%m/%d")].copy() if not df_log.empty else pd.DataFrame()
day_stats = {'cal':0, 'food':0, 'water':0, 'prot':0, 'fat':0}
supp_l, med_l = [], []
if not df_today.empty:
    for c in ['Cal_Sub', 'Net_Quantity', 'Prot_Sub', 'Fat_Sub']: df_today[c] = pd.to_numeric(df_today[c], errors='coerce').fillna(0)
    df_t_c = clean_duplicate_finish_records(df_today)
    f, w = calculate_intake_breakdown(df_t_c)
    day_stats.update({'cal': df_t_c['Cal_Sub'].sum(), 'food': f, 'water': w, 'prot': df_t_c['Prot_Sub'].sum(), 'fat': df_t_c['Fat_Sub'].sum()})
    # 保養品與藥品
    df_supp = df_today[df_today['Category'] == '保養品']
    if not df_supp.empty: supp_l = [{'name': k, 'count': v} for k, v in df_supp.groupby('Item_Name')['Net_Quantity'].sum().items()]
    df_med = df_today[df_today['Category'] == '藥品']
    if not df_med.empty: med_l = [{'name': k, 'count': v} for k, v in df_med.groupby('Item_Name')['Net_Quantity'].sum().items()]

st.markdown(render_header(rec_date.strftime("%Y年 %m月 %d日")), unsafe_allow_html=True)
col_dash, col_input = st.columns([4, 3], gap="medium")

# --- 左欄：Dashboard ---
with col_dash:
    with st.container(border=True):
        st.markdown("#### 📊 本日健康總覽")
        # 趨勢圖 (保留 V12.3 的強健解析)
        with st.expander("📈 飲食趨勢分析"):
            r_opt = st.radio("區間", ["近 7 天", "近 30 天", "自訂"], horizontal=True, label_visibility="collapsed")
            d_s = (tw_now.date() - timedelta(days=6 if "7" in r_opt else 29))
            d_range = st.date_input("選擇日期區間", value=(d_s, tw_now.date()))
            if isinstance(d_range, tuple) and len(d_range)==2:
                df_v = df_log.copy()
                temp_d = pd.to_datetime(df_v['Date'], errors='coerce')
                df_v = df_v[temp_d.notna()].copy(); df_v['D'] = temp_d[temp_d.notna()].dt.date
                df_tr = df_v[(df_v['D'] >= d_range[0]) & (df_v['D'] <= d_range[1])]
                if not df_tr.empty:
                    tr_d = []
                    for d, g in df_tr.groupby('D'):
                        f_n, w_n = calculate_intake_breakdown(clean_duplicate_finish_records(g))
                        tr_d.append({'Date': d, 'Cal': g['Cal_Sub'].sum(), 'Food': f_n, 'Water': w_n})
                    df_ch = pd.DataFrame(tr_d).sort_values('Date')
                    fig = make_subplots(specs=[[{"secondary_y": True}]])
                    fig.add_trace(go.Bar(x=df_ch['Date'], y=df_ch['Cal'], name="熱量", marker_color='#FFD700', opacity=0.6), secondary_y=False)
                    fig.add_trace(go.Bar(x=df_ch['Date'], y=df_ch['Food'], name="食量", marker_color='#90EE90', opacity=0.6), secondary_y=False)
                    fig.add_trace(go.Scatter(x=df_ch['Date'], y=df_ch['Water'], name="飲水", line=dict(color='#00BFFF', width=2)), secondary_y=True)
                    fig.update_layout(height=380, legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"), barmode='group', margin=dict(t=10,b=20))
                    st.plotly_chart(fig, width="stretch")
        
        # 今日指標 (修正：補回 HTML 指標顯示)
        with st.expander("📝 今日營養概況", expanded=st.session_state.dash_stat_open): 
            st.markdown(render_daily_stats_html(day_stats), unsafe_allow_html=True)
            st.markdown(render_supp_med_html(supp_l, med_l), unsafe_allow_html=True)

# --- 右欄：飲食紀錄 ---
with col_input:
    m_opts = ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "第六餐", "第七餐", "第八餐", "第九餐", "第十餐", "點心1", "點心2", "點心3"]
    m_stat = {m: " (已記)" for m in (df_today['Meal_Name'].unique() if not df_today.empty else [])}
    if not df_today.empty:
        for _, r in df_today[df_today['ItemID'].isin(['FINISH', 'WASTE'])].iterrows(): m_stat[r['Meal_Name']] = f" (已記) (完食: {str(r['Time'])[:5]})"
    if 'meal_selector' not in st.session_state: st.session_state.meal_selector = next((m for m in m_opts if m not in m_stat), m_opts[0])
    
    with st.container(border=True):
        st.markdown("#### 🍽️ 飲食紀錄")
        c_m, c_b = st.columns(2)
        meal_n = c_m.selectbox("餐別", m_opts, format_func=lambda m: f"{m}{m_stat.get(m, '')}", key="meal_selector")
        df_m = df_today[df_today['Meal_Name'] == meal_n] if not df_today.empty else pd.DataFrame()
        bowl_w = c_b.number_input("🥣 碗重 (g)", value=float(df_m.iloc[-1]['Bowl_Weight']) if not df_m.empty else 30.0, step=0.1)
        
        # 修正 2: 補回餐點明細表格
        if not df_m.empty:
            with st.expander(f"📜 查看 {meal_n} 已記錄明細"):
                view_df = df_m[['Item_Name', 'Net_Quantity', 'Cal_Sub', 'Time']].copy()
                def append_time_to_finish(row):
                    name_str = str(row['Item_Name'])
                    if '完食' in name_str or '剩食' in name_str:
                        t_str = str(row['Time'])[:5]
                        return f"{name_str} ({t_str})"
                    return name_str
                view_df['品名'] = view_df.apply(append_time_to_finish, axis=1)
                view_df = view_df[['品名', 'Net_Quantity', 'Cal_Sub']]
                view_df.columns = ['品名', '數量', '熱量']
                st.dataframe(view_df, width="stretch", hide_index=True)

        m_stats = {'food':0, 'water':0, 'cal':0, 'prot':0, 'fat':0}
        if not df_m.empty:
            df_m_c = clean_duplicate_finish_records(df_m); fm, wm = calculate_intake_breakdown(df_m_c)
            m_stats.update({'food':fm, 'water':wm, 'cal':df_m_c['Cal_Sub'].sum(), 'prot':df_m_c['Prot_Sub'].sum(), 'fat':df_m_c['Fat_Sub'].sum()})
        
        with st.expander("📊 本餐營養小計", expanded=st.session_state.meal_stats_open):
            st.markdown(render_meal_stats_simple(m_stats), unsafe_allow_html=True)
        
        st.divider(); st.markdown('<div id="input-anchor"></div>', unsafe_allow_html=True)
        nav = st.radio("模式", ["➕ 新增", "🏁 完食"], horizontal=True, label_visibility="collapsed", key="nav_mode")
        
        l_ref_w = st.session_state.cart[-1]['Scale_Reading'] if st.session_state.cart else (float(df_m[~df_m['ItemID'].isin(['WASTE', 'FINISH'])].iloc[-1]['Scale_Reading']) if not df_m.empty and not df_m[~df_m['ItemID'].isin(['WASTE', 'FINISH'])].empty else bowl_w)
        l_ref_n = st.session_state.cart[-1]['Item_Name'] if st.session_state.cart else (df_m[~df_m['ItemID'].isin(['WASTE', 'FINISH'])].iloc[-1]['Item_Name'] if not df_m.empty and not df_m[~df_m['ItemID'].isin(['WASTE', 'FINISH'])].empty else "碗")

        if nav == "➕ 新增":
            c1, c2 = st.columns(2)
            cat = c1.selectbox("類別", ["請選擇..."] + list(df_items['Category'].unique()), key="cat_select")
            item = c2.selectbox("品名", df_items[df_items['Category']==cat]['Item_Name'].tolist() if cat!="請選擇..." else ["選類別"], key="item_select")
            unit = unit_map.get(item, "g")
            
            c3, c4 = st.columns(2)
            with c3:
                sc_ui = st.number_input(f"讀數 ({unit})", step=0.1, key="scale_val", value=None, placeholder="輸入讀數")
                if unit in ["g", "ml"]:
                    st.caption(f"📏 前筆參考：{l_ref_w:.1f} {unit} ({l_ref_n})")
                    is_z = st.checkbox("⚖️ 已歸零 / 單獨秤重", key="check_zero")
                else: is_z = True
            
            sc_v = safe_float(sc_ui)
            if sc_ui is None: nw, msg = 0.0, "等待輸入"
            elif unit in ["g", "ml"]:
                if is_z: nw, msg = sc_v, "單獨秤重"
                else: nw, msg = (0.0, "⚠️ 異常：低於前筆") if (sc_v < l_ref_w) else (sc_v - l_ref_w, f"累加 (+{sc_v - l_ref_w:.1f})")
            else: nw, msg = sc_v, f"單位: {unit}"
            c4.metric("淨重", f"{nw:.1f}", delta=msg, delta_color="inverse" if "異常" in msg else "off")
            
            st.button("⬇️ 加入清單", type="secondary", width="stretch", disabled=(cat=="請選擇..." or sc_v<=0 or "異常" in msg), on_click=add_to_cart_callback, args=(bowl_w, l_ref_w, l_ref_n))
            
            if st.session_state.cart:
                st.markdown("##### 🛒 待存清單")
                ed_df = st.data_editor(pd.DataFrame(st.session_state.cart), width="stretch", column_config={"Item_Name": "品名", "Net_Quantity": "淨重", "Cal_Sub": "熱量"}, column_order=["Item_Name", "Net_Quantity", "Cal_Sub"], num_rows="fixed")
                
                # 修正 3: 解決刪除需點兩次的問題 (優化 Pop 邏輯)
                del_opts = ["請選擇項目刪除..."] + [f"{i+1}. {r['Item_Name']} ({r['Net_Quantity']})" for i, r in ed_df.iterrows()]
                del_idx_str = st.selectbox("🗑️ 快速刪除項目", del_opts)
                if del_idx_str != "請選擇項目刪除..." and st.button("確認刪除", type="secondary"):
                    idx = int(del_idx_str.split(".")[0]) - 1
                    st.session_state.cart.pop(idx)
                    st.rerun() # 強制刷新確保清單更新

                if st.button("💾 儲存寫入 Google Sheet", type="primary", width="stretch"):
                    rows = [[str(uuid.uuid4()), f"{rec_date.strftime('%Y/%m/%d')} {rec_time_str}:00", rec_date.strftime('%Y/%m/%d'), f"{rec_time_str}:00", meal_n, r['ItemID'], r['Category'], r['Scale_Reading'], r['Bowl_Weight'], r['Net_Quantity'], r['Cal_Sub'], r['Prot_Sub'], r['Fat_Sub'], r['Phos_Sub'], "", r['Item_Name'], ""] for _, r in ed_df.iterrows()]
                    sheet_log.append_rows(rows); st.toast("✅ 儲存成功"); st.session_state.cart = []; load_data.clear(); st.session_state.just_saved = True; st.rerun()

        elif nav == "🏁 完食":
            f_d = st.date_input("完食日期", value=rec_date); f_t = format_time_str(st.text_input("時間", value=get_tw_time().strftime("%H%M")))
            f_ty = st.radio("狀態", ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], horizontal=True)
            wn, wc = 0.0, 0.0
            if "剩" in f_ty:
                cw1, cw2 = st.columns(2)
                vg, vt = safe_float(cw1.number_input("總重 (容器+剩食)")), safe_float(cw2.number_input("容器重"))
                wn = vg - vt
                if wn > 0 and not df_m.empty:
                    calc = df_m[(~df_m['Category'].isin(['藥品','保養品'])) & (df_m['Net_Quantity']>0)]
                    if not calc.empty: wc = wn * (calc['Cal_Sub'].sum()/calc['Net_Quantity'].sum()); st.warning(f"📉 剩餘：{wn:.1f}g (約扣 {wc:.1f}kcal)")
            st.button("💾 紀錄完食", type="primary", width="stretch", on_click=save_finish_callback, args=(f_ty, wn, wc, bowl_w, meal_n, f_t, f_d, rec_date))