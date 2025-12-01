# V2.4 修正核心如下
# 雙向同步： 啟動時讀取 Log_Data，算出當日總量顯示在左側。
# 補登機制： 寫入時不再清空畫面，而是重新讀取資料，讓您看到剛剛加進去的東西，方便繼續加凍肉。
# 完食與剩食： 新增一個專屬區塊，用來記錄「時間區段」與「剩餘重量（負數扣除）」。
# 單位判斷： 加入 Unit_Type 判斷，如果是「顆」，就不除以 100。
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# --- 1. 設定頁面 (寬版) ---
st.set_page_config(page_title="大文餵食紀錄", page_icon="🐱", layout="wide")

# --- 小工具：確保數據是數字 ---
def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

# --- 連線設定 ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
    client = gspread.authorize(creds)
    return client

try:
    client = init_connection()
    spreadsheet = client.open("DaWen daily record")
    sheet_log = spreadsheet.worksheet("Log_Data")
    sheet_db = spreadsheet.worksheet("DB_Items")
except Exception as e:
    st.error(f"連線失敗：{e}")
    st.stop()

# --- 讀取資料 (加入 Log_Data 的讀取) ---
# TTL 設短一點 (10秒)，這樣寫入後能較快看到更新
@st.cache_data(ttl=10)
def load_data():
    db_data = sheet_db.get_all_records()
    log_data = sheet_log.get_all_records() # 新增讀取歷史紀錄
    return pd.DataFrame(db_data), pd.DataFrame(log_data)

df_items, df_log = load_data()

# 建立查詢字典 (Mapping)
if not df_items.empty:
    # 確保欄位名稱正確 (這裡加上 strip 避免 Excel 有空白鍵)
    df_items.columns = [c.strip() for c in df_items.columns]
    
    item_map = dict(zip(df_items['Item_Name'], df_items['ItemID']))
    
    # 營養與單位字典
    cal_map = dict(zip(df_items['Item_Name'], df_items['Ref_Cal_100g']))
    prot_map = dict(zip(df_items['Item_Name'], df_items['Protein_Pct']))
    fat_map = dict(zip(df_items['Item_Name'], df_items['Fat_Pct']))
    phos_map = dict(zip(df_items['Item_Name'], df_items['Phos_Pct']))
    cat_map = dict(zip(df_items['Item_Name'], df_items['Category']))
    unit_map = dict(zip(df_items['Item_Name'], df_items['Unit_Type'])) # 新增單位判斷
else:
    st.error("讀取不到 DB_Items")
    st.stop()

# ==========================================
#      左側 Dashboard (即時戰情室)
# ==========================================

st.title("🐱 大文餵食紀錄")

with st.sidebar:
    st.header("⚙️ 設定")
    
    # 日期時間設定
    record_date = st.date_input("📅 日期", datetime.now())
    # 將日期轉字串以便過濾 DataFrame
    str_date_filter = record_date.strftime("%Y/%m/%d")
    
    record_time = st.time_input("🕒 時間", datetime.now())
    st.divider()
    meal_name = st.selectbox("🍽️ 餐別", ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "點心"])
    
    # 自動帶入碗重邏輯 (進階)
    # 嘗試從 Log 中找今天同一餐的最後一筆碗重
    last_bowl = 30.0 # 預設值
    if not df_log.empty:
        # 過濾出今天、這一餐的紀錄
        mask = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
        today_meal_log = df_log[mask]
        if not today_meal_log.empty:
            # 抓最後一筆的碗重
            try:
                last_bowl = float(today_meal_log.iloc[-1]['Bowl_Weight'])
            except:
                pass

    bowl_weight = st.number_input("🥣 碗重 (g)", value=last_bowl, step=0.1)

    st.divider()
    
    # --- 📊 Dashboard 統計區 ---
    st.subheader(f"📊 {str_date_filter} 統計")
    
    if not df_log.empty:
        # 1. 過濾出「今天」的所有資料
        df_today = df_log[df_log['Date'] == str_date_filter].copy()
        
        # 轉換數值欄位 (防呆)
        df_today['Net_Quantity'] = pd.to_numeric(df_today['Net_Quantity'], errors='coerce').fillna(0)
        df_today['Cal_Sub'] = pd.to_numeric(df_today['Cal_Sub'], errors='coerce').fillna(0)
        
        # 計算總量
        # 排除 "水", "藥品", "保養品", "剩食" 才算食物重量
        food_mask = ~df_today['Category_Copy'].isin(['水', '藥品', '保養品', '剩食'])
        day_food_weight = df_today[food_mask]['Net_Quantity'].sum()
        day_calories = df_today['Cal_Sub'].sum()
        
        # 統計藥品 (去除重複，只顯示名稱)
        meds = df_today[df_today['Category_Copy'].isin(['藥品', '保養品'])]['ItemID'].unique() # 這裡假設 ItemID 是中文名，如果是代碼需轉換
        # 如果 Log 記的是代碼，這裡要做轉換，先假設 Log 裡的 ItemID 存的是名稱或有存名稱欄位
        # 為了簡單，我們直接讀 ItemID (假設您存的是品名，或者 Log 有 Item_Name 欄位)
        
        # 顯示 Metrics
        c1, c2 = st.columns(2)
        c1.metric("🔥 總熱量", f"{day_calories:.0f}")
        c2.metric("🍖 總食量", f"{day_food_weight:.0f}g")
        
        if len(meds) > 0:
            st.write("💊 已服用：")
            for m in meds:
                st.caption(f"- {m}")
    else:
        st.write("尚無今日紀錄")

    st.divider()
    
    # --- 該餐統計 (可點擊展開) ---
    st.subheader(f"🍽️ {meal_name} 小計")
    if not df_log.empty:
        # 過濾出「今天 + 該餐」
        mask_meal = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
        df_meal = df_log[mask_meal]
        
        if not df_meal.empty:
            df_meal['Net_Quantity'] = pd.to_numeric(df_meal['Net_Quantity'], errors='coerce').fillna(0)
            df_meal['Cal_Sub'] = pd.to_numeric(df_meal['Cal_Sub'], errors='coerce').fillna(0)
            
            meal_cal = df_meal['Cal_Sub'].sum()
            meal_weight = df_meal['Net_Quantity'].sum()
            
            st.metric("本餐熱量", f"{meal_cal:.0f} kcal")
            st.metric("本餐重量", f"{meal_weight:.1f} g")
            
            # 展開明細
            with st.expander("查看本餐明細"):
                # 只顯示重要欄位
                st.dataframe(df_meal[['ItemID', 'Net_Quantity', 'Cal_Sub']], hide_index=True)
        else:
            st.info("本餐尚未開始")

# ==========================================
#      主畫面：操作區
# ==========================================

# 1. 顯示該餐目前的狀態 (讓你知道加到哪了)
# ----------------------------------------
# 這裡我們不只顯示購物車，還要顯示「已經寫入資料庫」的內容，方便補登
if not df_log.empty:
    mask_meal_view = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
    df_meal_view = df_log[mask_meal_view]
    if not df_meal_view.empty:
        # 抓最後一筆的秤重，當作「上一筆」的參考
        try:
            last_scale_reading = float(df_meal_view.iloc[-1]['Scale_Reading'])
            last_item_name = df_meal_view.iloc[-1]['ItemID']
            st.info(f"💡 上一筆紀錄：{last_item_name} (秤重: {last_scale_reading}g)")
        except:
            last_scale_reading = bowl_weight
    else:
        last_scale_reading = bowl_weight # 如果是第一筆，基準就是碗重
else:
    last_scale_reading = bowl_weight

# 2. 新增品項區 (購物車)
# ----------------------------------------
if 'cart' not in st.session_state:
    st.session_state.cart = []

tab1, tab2 = st.tabs(["➕ 新增食物/藥品", "🏁 完食/紀錄剩餘"])

with tab1:
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            unique_cats = ["全部"] + list(df_items['Category'].unique())
            filter_cat = st.selectbox("1. 類別", unique_cats)
            if filter_cat == "全部":
                filtered_items = df_items['Item_Name'].tolist()
            else:
                filtered_items = df_items[df_items['Category'] == filter_cat]['Item_Name'].tolist()

        with c2:
            item_name = st.selectbox("2. 品名", filtered_items)

        # 取得單位，判斷是否為顆
        unit = unit_map.get(item_name, "g") 
        
        c3, c4 = st.columns(2)
        with c3:
            if unit in ["顆", "粒", "ml"]: # 這些單位通常不用扣碗重，直接輸入數量
                scale_reading = st.number_input(f"3. 數量 ({unit})", value=1.0, step=1.0, key="count_input")
                net_weight = scale_reading # 數量即淨重
                calc_msg = f"單位: {unit}"
                # 這裡的 scale_reading 為了資料庫統一，我們存數量，或者存 0 (視您需求)
                # 建議：如果是顆，Scale_Reading 存 0 或存數量，Net_Quantity 存數量
            else:
                scale_reading = st.number_input("3. 秤重 (g)", value=0.0, step=0.1, key="scale_input")
                
                # 自動判斷扣重邏輯：
                # 如果購物車有東西，扣購物車最後一筆
                # 如果購物車沒東西，扣「資料庫」最後一筆 (實現補登)
                if len(st.session_state.cart) > 0:
                    ref_weight = st.session_state.cart[-1]['Scale_Reading']
                    calc_msg = f"扣購物車前筆 {ref_weight}"
                else:
                    ref_weight = last_scale_reading
                    calc_msg = f"扣歷史前筆 {ref_weight}"
                
                net_weight = scale_reading - ref_weight

        with c4:
            st.metric("淨重/數量", f"{net_weight:.1f}", delta=calc_msg, delta_color="off")

        if st.button("⬇️ 加入清單", type="secondary", use_container_width=True):
            if scale_reading > 0:
                item_id = item_map.get(item_name, "")
                category = cat_map.get(item_name, "")
                
                # --- 營養計算核心修正 (Q6) ---
                cal_val = safe_float(cal_map.get(item_name, 0))
                prot_val = safe_float(prot_map.get(item_name, 0))
                fat_val = safe_float(fat_map.get(item_name, 0))
                phos_val = safe_float(phos_map.get(item_name, 0))

                if unit in ["顆", "粒"]:
                    # 如果是顆，公式 = 數量 * 單顆熱量 (假設 Excel 裡的 Ref_Cal_100g 填的是單顆熱量)
                    # 如果 Excel 填的是 100g 熱量，那您需要知道一顆幾克。
                    # 這裡假設：藥品/保養品 Excel 填的是「每顆」的數值
                    cal = net_weight * cal_val
                    prot = net_weight * prot_val
                    fat = net_weight * fat_val
                    phos = net_weight * phos_val
                else:
                    # 一般食物，公式 = 重量 * (每100g數值 / 100)
                    cal = net_weight * cal_val / 100
                    prot = net_weight * prot_val / 100
                    fat = net_weight * fat_val / 100
                    phos = net_weight * phos_val / 100

                st.session_state.cart.append({
                    "Category": category,
                    "ItemID": item_id,
                    "Item_Name": item_name,
                    "Scale_Reading": scale_reading,
                    "Bowl_Weight": bowl_weight,
                    "Net_Quantity": net_weight,
                    "Cal_Sub": cal,
                    "Prot_Sub": prot,
                    "Fat_Sub": fat,
                    "Phos_Sub": phos,
                    "Unit": unit # 紀錄單位方便除錯
                })
                st.success(f"已加入：{item_name}")
                st.rerun() # 重新整理以更新數據
            else:
                st.warning("請輸入數值")

    # 顯示購物車
    if st.session_state.cart:
        st.write("##### 🛒 待存清單")
        df_cart = pd.DataFrame(st.session_state.cart)
        st.dataframe(df_cart[["Item_Name", "Net_Quantity", "Cal_Sub"]], use_container_width=True)
        
        if st.button("💾 儲存寫入 Google Sheet", type="primary", use_container_width=True):
            with st.spinner("寫入中..."):
                rows = []
                str_date = record_date.strftime("%Y/%m/%d")
                # 使用當下時間，或者您可以讓使用者選時間，這裡先用當下
                now_time = datetime.now().strftime("%H:%M:%S")
                timestamp = f"{str_date} {now_time}"

                for item in st.session_state.cart:
                    row = [
                        str(uuid.uuid4()),      # LogID
                        timestamp,              # Timestamp
                        str_date,               # Date (新增這欄方便篩選)
                        now_time,               # Time
                        meal_name,              # Meal_Name
                        item['ItemID'],         # ItemID (代碼)
                        item['Category'],       # Category
                        item['Scale_Reading'],
                        item['Bowl_Weight'],
                        item['Net_Quantity'],
                        item['Cal_Sub'],
                        item['Prot_Sub'],
                        item['Fat_Sub'],
                        item['Phos_Sub'],
                        "",                     # 篩選類別 (Log這欄非必要，可留空)
                        item['Item_Name'],      # 這裡也可以存中文名備查
                        ""                      # Finish_Time
                    ]
                    rows.append(row)
                
                try:
                    # 注意：這裡 append_rows 可能會因為欄位數跟您的 Excel 不一樣而報錯
                    # 請務必確認 Log_Data 欄位順序！
                    # 目前假設順序：LogID, Timestamp, Date, Time, Meal_Name, ItemID, Category, Scale, Bowl, Net, Cal, Prot, Fat, Phos, ...
                    sheet_log.append_rows(rows)
                    st.toast("✅ 寫入成功！")
                    st.session_state.cart = []
                    # 清除快取，強制重讀 Google Sheet，這樣左邊的 Dashboard 才會更新
                    load_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"寫入失敗：{e}")

# 3. 完食/紀錄剩餘區 (Q1 & Q2)
# ----------------------------------------
with tab2:
    st.info("在此記錄完食時間，或扣除剩餘重量")
    
    with st.form("finish_form"):
        # 完食時間：允許輸入區段，例如 "1200-1255"
        # 為了方便，我們提供一個文字框，預設為當下時間
        default_time_str = datetime.now().strftime("%H:%M")
        finish_time_str = st.text_input("完食時間 (可填區段，如 12:00-12:30)", value=default_time_str)
        
        # 剩餘/完食狀態
        finish_type = st.radio("狀態", ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], horizontal=True)
        
        waste_net = 0.0
        waste_cal = 0.0
        
        if finish_type == "有剩餘 (需秤重)":
            # 這裡需要輸入「最後含碗總重」
            final_scale = st.number_input("剩餘含碗總重 (g)", min_value=0.0, step=0.1)
            # 剩餘淨重 = 最後總重 - 碗重
            if final_scale > 0:
                waste_net = final_scale - bowl_weight
                st.warning(f"剩餘淨重：{waste_net:.1f} g (將以負數寫入資料庫)")
                
                # 計算剩餘熱量 (Q6: 剩餘怎麼算？)
                # 這裡採用「加權平均法」：算出該餐平均熱量密度 (kcal/g) * 剩餘重量
                # 這是一個估算值
                if not df_log.empty:
                    mask_m = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
                    df_m = df_log[mask_m]
                    total_in_cal = pd.to_numeric(df_m['Cal_Sub'], errors='coerce').sum()
                    total_in_weight = pd.to_numeric(df_m['Net_Quantity'], errors='coerce').sum()
                    
                    if total_in_weight > 0:
                        avg_density = total_in_cal / total_in_weight
                        waste_cal = waste_net * avg_density
                        st.caption(f"預估扣除熱量：{waste_cal:.1f} kcal (依本餐平均密度計算)")

        submitted = st.form_submit_button("💾 記錄完食/剩餘")
        
        if submitted:
            # 寫入邏輯：
            # 1. 如果是全部吃光，只寫入一筆 "Finish_Time" 的紀錄，重量為 0
            # 2. 如果有剩，寫入一筆類別為 "剩食" 的紀錄，重量為負數
            
            str_date = record_date.strftime("%Y/%m/%d")
            now_time = datetime.now().strftime("%H:%M:%S")
            timestamp = f"{str_date} {now_time}"
            
            # 準備寫入的 Row
            # ItemID = "WASTE" 或 "FINISH"
            # Net_Quantity = -waste_net (負數)
            # Cal_Sub = -waste_cal (負數)
            
            row = [
                str(uuid.uuid4()),      # LogID
                timestamp,              # Timestamp
                str_date,               # Date
                now_time,               # Time
                meal_name,              # Meal_Name
                "WASTE" if waste_net > 0 else "FINISH", # ItemID
                "剩食",                 # Category
                0,                      # Scale_Reading (不重要)
                bowl_weight,            # Bowl_Weight
                -waste_net,             # Net_Quantity (負數！)
                -waste_cal,             # Cal_Sub (負數！)
                0, 0, 0,                # Prot, Fat, Phos (暫不扣除或依比例)
                "",                     # 篩選類別
                "完食紀錄",             # Item_Name
                finish_time_str         # Finish_Time (這裡寫入時間)
            ]
            
            try:
                sheet_log.append_row(row)
                st.toast("✅ 完食紀錄已儲存")
                load_data.clear() # 重讀
                st.rerun()
            except Exception as e:
                st.error(f"寫入失敗：{e}")





    
if False:
  """
  # V2.3 終極行動優化版 (Mobile Optimized)

import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# --- 1. 設定頁面資訊 ---
# layout="centered" 在手機上閱讀體驗通常比 wide 好，因為視線集中
# 但為了電腦版也不錯，我們維持 wide，靠內部排版來控制
st.set_page_config(page_title="大文餵食紀錄", page_icon="🐱", layout="wide")

# --- 連線設定 (雲端版) ---
@st.cache_resource
def init_connection():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    # 改成從 Streamlit 的 Secrets 讀取，而不是讀檔案
    # 注意：這裡的 "gcp_service_account" 要跟您在 Secrets 裡設定的標題一樣
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
    st.error(f"連線失敗：{e}")
    st.stop()

# --- 讀取資料 ---
@st.cache_data(ttl=60)

# --- 小工具：確保數據是數字 ---
def safe_float(value):
    try:
        # 嘗試轉成浮點數
        return float(value)
    except (ValueError, TypeError):
        # 如果失敗（例如是空字串、文字），就回傳 0.0
        return 0.0

def load_data():
    data = sheet_db.get_all_records()
    return pd.DataFrame(data)

df_items = load_data()

if not df_items.empty:
    item_map = dict(zip(df_items['Item_Name'], df_items['ItemID']))
    cal_map = dict(zip(df_items['Item_Name'], df_items['Ref_Cal_100g']))
    prot_map = dict(zip(df_items['Item_Name'], df_items['Protein_Pct']))
    fat_map = dict(zip(df_items['Item_Name'], df_items['Fat_Pct']))
    phos_map = dict(zip(df_items['Item_Name'], df_items['Phos_Pct']))
    cat_map = dict(zip(df_items['Item_Name'], df_items['Category']))
else:
    st.error("讀取不到 DB_Items")
    st.stop()

# ==========================================
#      手機版優化介面開始
# ==========================================

st.title("🐱 大文餵食紀錄")

# --- 側邊欄：放置基本設定 (手機版會變成漢堡選單) ---
with st.sidebar:
    st.header("⚙️ 環境設定")
    # 把日期時間放這裡，手機上就不會佔據主畫面空間
    record_date = st.date_input("📅 日期", datetime.now())
    record_time = st.time_input("🕒 時間", datetime.now())
    st.divider()
    meal_name = st.selectbox("🍽️ 餐別", ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "點心"])
    bowl_weight = st.number_input("🥣 碗重 (g)", value=30.0, step=0.1)
    
    # 手機版側邊欄底部顯示目前狀態
    st.info(f"餐別：{meal_name}\n碗重：{bowl_weight}g")

# --- 主畫面：購物車邏輯 ---
if 'cart' not in st.session_state:
    st.session_state.cart = []

# 使用 container 讓輸入區塊在手機上有卡片感
with st.container(border=True):
    st.subheader("➕ 新增品項")
    
    # 【手機版面策略】
    # 電腦版：4欄一列
    # 手機版：Streamlit 會自動把 columns 堆疊。
    # 但為了更好按，我們拆成 [類別+品名] 一列，[秤重+淨重] 一列
    
    # 第一列：選食物
    c1, c2 = st.columns(2)
    with c1:
        unique_cats = ["全部"] + list(df_items['Category'].unique())
        filter_cat = st.selectbox("1. 類別", unique_cats)
        if filter_cat == "全部":
            filtered_items = df_items['Item_Name'].tolist()
        else:
            filtered_items = df_items[df_items['Category'] == filter_cat]['Item_Name'].tolist()

    with c2:
        item_name = st.selectbox("2. 品名", filtered_items)

    # 第二列：輸入重量與顯示
    c3, c4 = st.columns(2)
    with c3:
        # 手機上 number_input 會叫出數字鍵盤，很好用
        scale_reading = st.number_input("3. 秤重 (g)", value=0.0, step=0.1, key="scale")

    # 計算淨重
    current_cart_len = len(st.session_state.cart)
    if current_cart_len == 0:
        ref_weight = bowl_weight 
        calc_msg = "扣碗重"
    else:
        ref_weight = st.session_state.cart[-1]['Scale_Reading']
        calc_msg = f"扣上一筆 {ref_weight}"
    net_weight = scale_reading - ref_weight

    with c4:
        # 使用 metric 顯示大大的數字，手機閱讀性高
        st.metric("淨重 (g)", f"{net_weight:.1f}", delta=calc_msg, delta_color="off")

    # 加入按鈕 - 【重點】use_container_width=True 讓按鈕變全寬，手機好按
    if st.button("⬇️ 加入清單", type="secondary", use_container_width=True):
        if scale_reading > 0:
            item_id = item_map.get(item_name, "")
            category = cat_map.get(item_name, "")
            # 營養計算 (加裝 safe_float 防護罩)
            cal_val = safe_float(cal_map.get(item_name, 0))
            prot_val = safe_float(prot_map.get(item_name, 0))
            fat_val = safe_float(fat_map.get(item_name, 0))
            phos_val = safe_float(phos_map.get(item_name, 0))

            cal = net_weight * cal_val / 100
            prot = net_weight * prot_val / 100
            fat = net_weight * fat_val / 100
            phos = net_weight * phos_val / 100            
            
            # 營養計算
            # cal = net_weight * cal_map.get(item_name, 0) / 100
            # prot = net_weight * prot_map.get(item_name, 0) / 100
            # fat = net_weight * fat_map.get(item_name, 0) / 100
            # phos = net_weight * phos_map.get(item_name, 0) / 100
            

            st.session_state.cart.append({
                "Category": category,
                "ItemID": item_id,
                "Item_Name": item_name,
                "Scale_Reading": scale_reading,
                "Bowl_Weight": bowl_weight,
                "Net_Quantity": net_weight,
                "Cal_Sub": cal,
                "Prot_Sub": prot,
                "Fat_Sub": fat,
                "Phos_Sub": phos,
                "Ref_Weight": ref_weight
            })
            st.success(f"已加入：{item_name}")
        else:
            st.warning("請輸入重量")

# --- 顯示清單與存檔 ---
st.subheader("🛒 本餐明細")

if st.session_state.cart:
    df_cart = pd.DataFrame(st.session_state.cart)
    
    # 手機版表格不宜太寬，只顯示最關鍵資訊
    st.dataframe(
        df_cart[["Item_Name", "Net_Quantity", "Cal_Sub"]], 
        use_container_width=True,
        column_config={
            "Item_Name": "品名",
            "Net_Quantity": "淨重(g)",
            "Cal_Sub": "熱量"
        },
        hide_index=True
    )
    
    total_cal = df_cart['Cal_Sub'].sum()
    total_net = df_cart['Net_Quantity'].sum()
    
    # 總結區塊
    m1, m2 = st.columns(2)
    m1.metric("🔥 總熱量", f"{total_cal:.1f}")
    m2.metric("⚖️ 總攝取", f"{total_net:.1f} g")
    
    st.divider()

    # 存檔按鈕 - 設為全寬，並使用 Primary 色系 (顯眼)
    if st.button("💾 確認儲存 (Save)", type="primary", use_container_width=True):
        with st.spinner("正在寫入雲端..."):
            rows_to_append = []
            str_date = record_date.strftime("%Y/%m/%d")
            str_time = record_time.strftime("%H:%M:%S")
            str_timestamp = f"{str_date} {str_time}"

            for item in st.session_state.cart:
                row = [
                    str(uuid.uuid4()),      # 1
                    str_timestamp,          # 2
                    meal_name,              # 3
                    item['ItemID'],         # 4
                    item['Category'],       # 5
                    item['Scale_Reading'],  # 6
                    item['Bowl_Weight'],    # 7
                    item['Net_Quantity'],   # 8
                    item['Cal_Sub'],        # 9
                    item['Prot_Sub'],       # 10
                    item['Fat_Sub'],        # 11
                    item['Phos_Sub'],       # 12
                    item['Category'],       # 13
                    item['Ref_Weight'],     # 14
                    ""                      # 15
                ]
                rows_to_append.append(row)

            try:
                sheet_log.append_rows(rows_to_append)
                st.balloons()
                st.success("✅ 寫入成功！")
                st.session_state.cart = []
            except Exception as e:
                st.error(f"寫入失敗：{e}")

    # 清空按鈕 - 稍微小一點，避免誤觸
    if st.button("🗑️ 清空重選", use_container_width=True):
        st.session_state.cart = []
  
  #V2.1 修正版 的 app.py 完整代碼
  import streamlit as st
  import pandas as pd
  import gspread
  from oauth2client.service_account import ServiceAccountCredentials
  from datetime import datetime
  import uuid

  # --- 設定頁面資訊 ---
  st.set_page_config(page_title="大文餵食紀錄", page_icon="🐱")

  # --- 1. 連線設定 ---
  @st.cache_resource
  def init_connection():
      scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
      creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
      client = gspread.authorize(creds)
      return client

  try:
      client = init_connection()
      spreadsheet = client.open("DaWen daily record")
      sheet_log = spreadsheet.worksheet("Log_Data")
      sheet_db = spreadsheet.worksheet("DB_Items")
  except Exception as e:
      st.error(f"連線失敗：{e}")
      st.stop()

  # --- 2. 讀取 DB_Items ---
  @st.cache_data(ttl=60)
  def load_data():
      data = sheet_db.get_all_records()
      return pd.DataFrame(data)

  df_items = load_data()

  if not df_items.empty:
      item_map = dict(zip(df_items['Item_Name'], df_items['ItemID']))
      # 建立營養成分對照表 (確保欄位名稱跟 Excel DB_Items 一樣)
      cal_map = dict(zip(df_items['Item_Name'], df_items['Ref_Cal_100g']))
      prot_map = dict(zip(df_items['Item_Name'], df_items['Protein_Pct']))
      fat_map = dict(zip(df_items['Item_Name'], df_items['Fat_Pct']))
      phos_map = dict(zip(df_items['Item_Name'], df_items['Phos_Pct']))
      cat_map = dict(zip(df_items['Item_Name'], df_items['Category']))
  else:
      st.error("讀取不到 DB_Items")
      st.stop()

  # --- 3. 輸入介面 ---
  st.title("🐱 大文餵食紀錄 (Python版)")

  col1, col2 = st.columns(2)
  with col1:
      record_date = st.date_input("📅 日期", datetime.now())
  with col2:
      record_time = st.time_input("🕒 時間", datetime.now())

  meal_name = st.selectbox("🍽️ 餐別", ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "點心"])
  bowl_weight = st.number_input("🥣 碗重 (g)", value=30.0, step=0.1)

  st.divider()

  # --- 4. 購物車邏輯 ---
  if 'cart' not in st.session_state:
      st.session_state.cart = []

  st.subheader("➕ 新增品項")

  c1, c2, c3 = st.columns([2, 1, 1])

  with c1:
      # 類別篩選
      unique_cats = ["全部"] + list(df_items['Category'].unique())
      filter_cat = st.selectbox("篩選類別", unique_cats)
      
      if filter_cat == "全部":
          filtered_items = df_items['Item_Name'].tolist()
      else:
          filtered_items = df_items[df_items['Category'] == filter_cat]['Item_Name'].tolist()
          
      item_name = st.selectbox("品名", filtered_items)

  with c2:
      scale_reading = st.number_input("⚖️ 秤重 (g)", value=0.0, step=0.1, key="scale")

  # --- 計算淨重邏輯 ---
  current_cart_len = len(st.session_state.cart)
  if current_cart_len == 0:
      ref_weight = bowl_weight # 第一筆，基準是碗重
  else:
      # 抓上一筆的秤重當作基準
      ref_weight = st.session_state.cart[-1]['Scale_Reading']

  net_weight = scale_reading - ref_weight

  with c3:
      st.metric("淨重", f"{net_weight:.1f} g")

  # 加入按鈕
  if st.button("⬇️ 加入"):
      if scale_reading > 0:
          # 準備資料
          item_id = item_map.get(item_name, "")
          category = cat_map.get(item_name, "")
          
          # 營養計算
          cal = net_weight * cal_map.get(item_name, 0) / 100
          prot = net_weight * prot_map.get(item_name, 0) / 100
          fat = net_weight * fat_map.get(item_name, 0) / 100
          phos = net_weight * phos_map.get(item_name, 0) / 100

          st.session_state.cart.append({
              "Category": category,
              "ItemID": item_id,
              "Item_Name": item_name,
              "Scale_Reading": scale_reading,
              "Bowl_Weight": bowl_weight,
              "Net_Quantity": net_weight,
              "Cal_Sub": cal,
              "Prot_Sub": prot,
              "Fat_Sub": fat,
              "Phos_Sub": phos,
              "Ref_Weight": ref_weight # 這裡要把扣除基準存下來，寫入 DB 用
          })
          st.success(f"已加入：{item_name}")
      else:
          st.warning("請輸入重量")

  # --- 5. 顯示與存檔 ---
  st.subheader("🛒 本餐明細")

  if st.session_state.cart:
      df_cart = pd.DataFrame(st.session_state.cart)
      # 顯示部分欄位給使用者確認
      st.dataframe(df_cart[["Category", "Item_Name", "Scale_Reading", "Net_Quantity"]], use_container_width=True)
      
      total_cal = df_cart['Cal_Sub'].sum()
      st.info(f"🔥 總熱量：{total_cal:.1f} kcal")

      if st.button("💾 儲存寫入 Google Sheet", type="primary"):
          with st.spinner("正在寫入..."):
              rows_to_append = []
              
              # 格式化時間字串
              str_date = record_date.strftime("%Y/%m/%d") # 確保日期格式
              str_time = record_time.strftime("%H:%M:%S")
              str_timestamp = f"{str_date} {str_time}"

              for item in st.session_state.cart:
                  # -------------------------------------------------------------
                  # 【嚴格對照】欄位順序修正版
                  # -------------------------------------------------------------
                  row = [
                      str(uuid.uuid4()),      # 1. LogID (產生亂碼)
                      str_timestamp,          # 2. Timestamp
                      meal_name,              # 3. Meal_Name
                      item['ItemID'],         # 4. ItemID
                      item['Category'],       # 5. Category_Copy
                      item['Scale_Reading'],  # 6. Scale_Reading
                      item['Bowl_Weight'],    # 7. Bowl_Weight
                      item['Net_Quantity'],   # 8. Net_Quantity
                      item['Cal_Sub'],        # 9. Cal_Sub
                      item['Prot_Sub'],       # 10. Prot_Sub
                      item['Fat_Sub'],        # 11. Fat_Sub
                      item['Phos_Sub'],       # 12. Phos_Sub
                      item['Category'],       # 13. 篩選類別 (填入類別即可)
                      item['Ref_Weight'],     # 14. Reference_Weight (這次計算扣除的基準)
                      ""                      # 15. Finish_Time (完食時間，先留空)
                  ]
                  rows_to_append.append(row)

              try:
                  sheet_log.append_rows(rows_to_append)
                  st.balloons()
                  st.success("✅ 寫入成功！請去 Google Sheet 確認資料。")
                  st.session_state.cart = [] # 清空購物車，準備記下一餐
              except Exception as e:
                  st.error(f"寫入失敗：{e}")

  # 清空按鈕
  if st.button("🗑️ 清空重選"):
      st.session_state.cart = []

    ------------------------------------------------------------------------
    第一版程式存參
    import streamlit as st
    import pandas as pd
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    from datetime import datetime

    #-- 設定頁面資訊 --
    st.set_page_config(page_title="大文餵食紀錄", page_icon="🐈‍⬛")

    #--1. 連線到google sheet --
    # 這是 Python 連接 Google Sheet 的標準起手式
    # @st.cach_resource 是一個「裝飾器」，讓 Streamlit 記住連線，不用每次重新整理都重連，速度會變快
    @st.cache_resource
    def init_connection():
      scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
      # 讀取我們放在資料夾裡的鑰匙
      creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
      client = gspread.authorize(creds)
      return client

    try:
      client = init_connection()
      # 打開你的試表（請認確名稱完全一致）
      # 注意：這裡改成你的 Google Sheet 檔案名稱
      sheet = client.open("DaWen daily record").worksheet("Log_Data")
      # 讀取 DB_Items 以便做下拉選單（之後實作，目前先寫死的）
      # db_sheet =  client.open("DaWen daily record").worksheet("DB_Items")
    except Exception as e:
      st.error(f"連線失敗，請檢查 JSON 檔名或試算名稱。\n錯誤訊息:{e}")
      st.stop() #停止執行

    # ---2. 標題與基本設定 --
    st.title("大文餵食紀錄")

    # 使用 columns 讓版面變成左右兩欄，比較好看
    col1, col2 = st.columns(2)
    with col1:
      # 預設為今天
      record_time = st.date_input("📅 日期", datetime.now())
    with col2:
      # 預設為現在時間
      record_time = st.time_input("🕒 時間", datetime.now())

    # 餐點選擇
    meal_name = st.selectbox("🍽️ 餐別", ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "點心"])

    # 碗重（可以手動改，預設30）
    bowl_weight = st.number_input("🥣 碗重 (g)", value=30.0, step=0.1)

    st.divider() # 畫一條分隔線

    # -- 3. 購物車邏輯（Session State）--
    # Streamlit 的特性是每次按按鈕都會從頭執行。
    # 所以我們需要用 sussion_state 這個（暫存區）來記住使用者剛加了什麼食物。

    if 'cart' not in st.session_state:
      st.session_state.cart = [] # 初始化一個空的購物車

    st.subheader("➕ 新增品項")

    # 輸入區塊
    c1, c2, c3 = st.columns([2,1,1,])
    with c1:
      # 這裡未來可以改造成從 Google Sheet DB_Items 讀取選單
      category = st.selectbox("類別",["主食", "副食", "鮮食", "凍肉", "水", "保養品", "藥品"])
      # 根據類別可以做第二層選單（暫時先用手輸或簡單選單代替）
      item_name = st.text_input("品名", value="雞肉" if category=="主食" else"") 

    with c2:
      scale_reading = st.number_input("⚖️ 秤重讀數 (g)", value=0.0, step=0.1, key="input_scale")

    # --- 自動計算淨重邏輯 (您的核心需求) ---
    # 邏輯：如果是第一筆，扣碗重；如果是第二筆之後，扣上一筆的秤重。
    current_cart_len = len(st.session_state.cart)

    if current_cart_len == 0:
        # 購物車是空的，基準是碗重
        ref_weight = bowl_weight
        calc_desc = f"(秤重 {scale_reading} - 碗重 {bowl_weight})"
    else:
        # 購物車有東西，基準是「上一筆的秤重讀數」
        last_item = st.session_state.cart[-1]
        ref_weight = last_item['Scale_Reading']
        calc_desc = f"(秤重 {scale_reading} - 上次 {ref_weight})"

    # 計算淨重
    net_weight = scale_reading - ref_weight

    with c3:
        st.metric("🥩 淨重", f"{net_weight:.1f} g")
        st.caption(calc_desc)

    # 加入按鈕
    if st.button("⬇️ 加入清單", type="secondary"):
        if scale_reading > 0 or category in ["保養品", "藥品"]: # 簡單防呆
            # 把資料包成一個字典 (Dictionary)，存入暫存區
            st.session_state.cart.append({
                "Category": category,
                "Item": item_name,
                "Scale_Reading": scale_reading,
                "Net_Weight": net_weight,
                "Ref_Weight": ref_weight # 記錄是用什麼扣的，方便除錯
            })
            st.success(f"已加入：{item_name} ({net_weight}g)")
            # 這裡有個小技巧：Rerun 可以讓畫面立刻更新，清空輸入框 (Streamlit特性)
        else:
            st.warning("請輸入重量！")

    # --- 4. 顯示目前清單與送出 ---
    st.subheader("🛒 本餐明細")

    if len(st.session_state.cart) > 0:
        # 把暫存區轉成表格顯示
        df = pd.DataFrame(st.session_state.cart)
        # 顯示表格，並隱藏 Ref_Weight 欄位 (那是給系統看的)
        st.dataframe(df[["Category", "Item", "Scale_Reading", "Net_Weight"]], use_container_width=True)

        # 計算總重 (排除水、藥品)
        food_total = df[~df['Category'].isin(['水', '藥品', '保養品'])]['Net_Weight'].sum()
        water_total = df[df['Category'] == '水']['Net_Weight'].sum()
        
        st.info(f"🍖 食物總重：{food_total:.1f} g  |  💧 喝水：{water_total:.1f} g")

        # 送出按鈕
        if st.button("💾 儲存到 Google Sheet", type="primary"):
            with st.spinner("正在寫入雲端..."):
                # 準備要寫入的資料列表
                rows_to_append = []
                
                # 格式化日期時間
                str_date = record_date.strftime("%Y/%m/%d")
                str_time = record_time.strftime("%H:%M:%S")
                timestamp = f"{str_date} {str_time}"

                for item in st.session_state.cart:
                    # 這裡的順序必須跟您 Google Sheet "Log_Data" 的欄位順序完全一樣！
                    # 假設您的順序是: LogID, Timestamp, Meal_Name, ItemID, Scale_Reading, Bowl_Weight, Net_Quantity...
                    # 這裡我們先簡化寫入幾個核心欄位，之後再對應完整欄位
                    
                    # 產生一個隨機 ID (Python 內建)
                    import uuid
                    log_id = str(uuid.uuid4())[:8]

                    row = [
                        log_id,          # LogID
                        timestamp,       # Timestamp
                        str_date,        # Date
                        str_time,        # Time
                        meal_name,       # Meal_Name
                        item['Item'],    # ItemID (暫時填名稱)
                        item['Category'],# Category
                        item['Scale_Reading'],
                        bowl_weight,
                        item['Net_Weight']
                    ]
                    rows_to_append.append(row)

                # 一次寫入多行 (比一行一行寫快很多)
                try:
                    sheet.append_rows(rows_to_append)
                    st.balloons() # 放氣球慶祝
                    st.success("✅ 寫入成功！")
                    st.session_state.cart = [] # 清空購物車
                except Exception as e:
                    st.error(f"寫入失敗：{e}")

    else:
        st.caption("尚未加入任何項目...")

    # 重置按鈕
    if st.button("🗑️ 清空重選"):
        st.session_state.cart = []

    """

    st.write("這行也不會執行")