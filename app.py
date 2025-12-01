# Python 程式碼 V3.1 (智慧防呆版)
import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import uuid

# --- 1. 設定頁面 ---
st.set_page_config(page_title="大文餵食紀錄", page_icon="🐱", layout="wide")

# --- 小工具 ---
def safe_float(value):
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0

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
@st.cache_data(ttl=10)
def load_data():
    db_data = sheet_db.get_all_records()
    log_data = sheet_log.get_all_records()
    return pd.DataFrame(db_data), pd.DataFrame(log_data)

df_items, df_log = load_data()

# 建立查詢字典
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
#      左側 Dashboard
# ==========================================
st.title("🐱 大文餵食紀錄")

with st.sidebar:
    st.header("⚙️ 設定")
    record_date = st.date_input("📅 日期", datetime.now())
    str_date_filter = record_date.strftime("%Y/%m/%d")
    record_time = st.time_input("🕒 時間", datetime.now())
    st.divider()
    meal_name = st.selectbox("🍽️ 餐別", ["第一餐", "第二餐", "第三餐", "第四餐", "第五餐", "點心"])
    
    # 自動抓取最後一次碗重
    last_bowl = 30.0
    if not df_log.empty:
        mask = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
        today_meal_log = df_log[mask]
        if not today_meal_log.empty:
            try:
                last_bowl = float(today_meal_log.iloc[-1]['Bowl_Weight'])
            except:
                pass
    bowl_weight = st.number_input("🥣 碗重 (g)", value=last_bowl, step=0.1)

    st.divider()
    # 統計區
    st.subheader(f"📊 {str_date_filter} 統計")
    if not df_log.empty:
        df_today = df_log[df_log['Date'] == str_date_filter].copy()
        df_today['Net_Quantity'] = pd.to_numeric(df_today['Net_Quantity'], errors='coerce').fillna(0)
        df_today['Cal_Sub'] = pd.to_numeric(df_today['Cal_Sub'], errors='coerce').fillna(0)
        
        food_mask = ~df_today['Category_Copy'].isin(['水', '藥品', '保養品', '剩食'])
        day_food_weight = df_today[food_mask]['Net_Quantity'].sum()
        day_calories = df_today['Cal_Sub'].sum()
        
        c1, c2 = st.columns(2)
        c1.metric("🔥 總熱量", f"{day_calories:.0f}")
        c2.metric("🍖 總食量", f"{day_food_weight:.0f}g")
        
        meds = df_today[df_today['Category_Copy'].isin(['藥品', '保養品'])]['Item_Name'].unique()
        if len(meds) > 0:
            st.write("💊 已服用：")
            for m in meds:
                st.caption(f"- {m}")
    else:
        st.write("尚無今日紀錄")

# ==========================================
#      主畫面：操作區
# ==========================================

# 1. 計算上一筆參考重量 (Ref Weight)
# ----------------------------------------
# 邏輯：先看購物車最後一筆 -> 沒有的話看資料庫最後一筆 -> 再沒有就是碗重
if 'cart' not in st.session_state:
    st.session_state.cart = []

last_scale_reading = bowl_weight # 預設值
last_item_name = "碗"

# A. 先檢查資料庫 (補登用)
if not df_log.empty:
    mask_meal_view = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
    df_meal_view = df_log[mask_meal_view]
    if not df_meal_view.empty:
        try:
            last_scale_reading = float(df_meal_view.iloc[-1]['Scale_Reading'])
            last_item_name = df_meal_view.iloc[-1]['Item_Name']
        except:
            pass

# B. 再檢查購物車 (如果購物車有新東西，以購物車為準)
if len(st.session_state.cart) > 0:
    last_scale_reading = st.session_state.cart[-1]['Scale_Reading']
    last_item_name = st.session_state.cart[-1]['Item_Name']

# 顯示提示
st.info(f"💡 目前累積重量：{last_scale_reading} g ({last_item_name})")


# 2. 新增品項區
# ----------------------------------------
tab1, tab2 = st.tabs(["➕ 新增食物/藥品", "🏁 完食/紀錄剩餘"])

with tab1:
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            unique_cats = ["請選擇..."] + list(df_items['Category'].unique()) # 增加請選擇，強制必選
            filter_cat = st.selectbox("1. 類別 (必選)", unique_cats)
            
            if filter_cat == "請選擇...":
                filtered_items = []
            elif filter_cat == "全部":
                filtered_items = df_items['Item_Name'].tolist()
            else:
                filtered_items = df_items[df_items['Category'] == filter_cat]['Item_Name'].tolist()

        with c2:
            item_name = st.selectbox("2. 品名 (必選)", filtered_items if filtered_items else ["請先選類別"])

        # 取得單位
        unit = unit_map.get(item_name, "g")
        
        # --- 核心邏輯：輸入與計算 ---
        c3, c4 = st.columns(2)
        
        with c3:
            if unit in ["顆", "粒", "ml"]:
                scale_reading = st.number_input(f"3. 數量 ({unit})", value=0.0, step=1.0, key="count_input")
                net_weight = scale_reading
                calc_msg = f"單位: {unit}"
                is_independent = True # 顆數視為獨立
            else:
                # 預設值設為上一筆，方便累加
                scale_reading = st.number_input("3. 秤重讀數 (g)", value=0.0, step=0.1, key="scale_input")
                
                # 防呆與邏輯判斷
                is_independent = False # 預設是累加
                
                if scale_reading > 0:
                    if scale_reading < last_scale_reading:
                        # ⚠️ 情況：輸入值 < 上一筆 -> 觸發防呆確認
                        st.warning(f"⚠️ 數值 ({scale_reading}) 小於上一筆 ({last_scale_reading})！")
                        is_independent = st.checkbox("✅ 是的，這是單獨秤重 (已歸零/分裝)", value=False)
                        
                        if is_independent:
                            # 模式 A: 單獨秤重 -> 淨重 = 輸入值
                            net_weight = scale_reading
                            calc_msg = "單獨秤重"
                        else:
                            # 模式 B: 輸入錯誤 -> 淨重無效
                            net_weight = 0.0
                            calc_msg = "⚠️ 請確認數值"
                    else:
                        # 正常累加模式 -> 淨重 = 輸入值 - 上一筆
                        net_weight = scale_reading - last_scale_reading
                        calc_msg = f"扣除前筆 {last_scale_reading}"
                else:
                    net_weight = 0.0
                    calc_msg = "請輸入重量"

        with c4:
            # 顯示計算結果
            if calc_msg == "⚠️ 請確認數值":
                st.error(calc_msg)
            else:
                st.metric("淨重/數量", f"{net_weight:.1f}", delta=calc_msg, delta_color="off")

        # --- 加入按鈕 ---
        # 必填檢查：1.類別有選 2.重量>0 3.如果觸發防呆，必須勾選確認
        btn_disabled = False
        if filter_cat == "請選擇..." or item_name == "請先選類別":
            btn_disabled = True
        if scale_reading <= 0:
            btn_disabled = True
        if scale_reading < last_scale_reading and not is_independent and unit not in ["顆", "粒", "ml"] and scale_reading > 0:
            btn_disabled = True # 卡住不給按

        if st.button("⬇️ 加入清單", type="secondary", use_container_width=True, disabled=btn_disabled):
            # 準備資料
            item_id = item_map.get(item_name, "")
            category = cat_map.get(item_name, "")
            
            # 營養計算
            cal_val = safe_float(cal_map.get(item_name, 0))
            prot_val = safe_float(prot_map.get(item_name, 0))
            fat_val = safe_float(fat_map.get(item_name, 0))
            phos_val = safe_float(phos_map.get(item_name, 0))

            if unit in ["顆", "粒"]:
                cal = net_weight * cal_val
                prot = net_weight * prot_val
                fat = net_weight * fat_val
                phos = net_weight * phos_val
            else:
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
                "Unit": unit
            })
            st.success(f"已加入：{item_name}")
            st.rerun()

    # 顯示購物車
    if st.session_state.cart:
        st.write("##### 🛒 待存清單")
        df_cart = pd.DataFrame(st.session_state.cart)
        st.dataframe(df_cart[["Item_Name", "Net_Quantity", "Cal_Sub"]], use_container_width=True)
        
        if st.button("💾 儲存寫入 Google Sheet", type="primary", use_container_width=True):
            with st.spinner("寫入中..."):
                rows = []
                str_date = record_date.strftime("%Y/%m/%d")
                now_time = datetime.now().strftime("%H:%M:%S")
                timestamp = f"{str_date} {now_time}"

                for item in st.session_state.cart:
                    row = [
                        str(uuid.uuid4()),      # 1. LogID
                        timestamp,              # 2. Timestamp
                        str_date,               # 3. Date
                        now_time,               # 4. Time
                        meal_name,              # 5. Meal_Name
                        item['ItemID'],         # 6. ItemID
                        item['Category'],       # 7. Category
                        item['Scale_Reading'],  # 8. Scale_Reading
                        item['Bowl_Weight'],    # 9. Bowl_Weight
                        item['Net_Quantity'],   # 10. Net_Quantity
                        item['Cal_Sub'],        # 11. Cal_Sub
                        item['Prot_Sub'],       # 12. Prot_Sub
                        item['Fat_Sub'],        # 13. Fat_Sub
                        item['Phos_Sub'],       # 14. Phos_Sub
                        "",                     # 15. 篩選類別
                        item['Item_Name'],      # 16. Item_Name
                        ""                      # 17. Finish_Time
                    ]
                    rows.append(row)
                
                try:
                    sheet_log.append_rows(rows)
                    st.toast("✅ 寫入成功！")
                    st.session_state.cart = []
                    load_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"寫入失敗：{e}")

# 3. 完食區 (維持 V3.0 邏輯)
# ----------------------------------------
with tab2:
    st.info("在此記錄完食時間，或扣除剩餘重量")
    with st.form("finish_form"):
        default_time_str = datetime.now().strftime("%H:%M")
        finish_time_str = st.text_input("完食時間 (如 12:00-12:30)", value=default_time_str)
        finish_type = st.radio("狀態", ["全部吃光 (盤光光)", "有剩餘 (需秤重)"], horizontal=True)
        
        waste_net = 0.0
        waste_cal = 0.0
        
        if finish_type == "有剩餘 (需秤重)":
            final_scale = st.number_input("剩餘含碗總重 (g)", min_value=0.0, step=0.1)
            if final_scale > 0:
                waste_net = final_scale - bowl_weight
                st.warning(f"剩餘淨重：{waste_net:.1f} g")
                # 熱量估算邏輯... (同 V3.0)
                if not df_log.empty:
                    mask_m = (df_log['Date'] == str_date_filter) & (df_log['Meal_Name'] == meal_name)
                    df_m = df_log[mask_m]
                    total_in_cal = pd.to_numeric(df_m['Cal_Sub'], errors='coerce').sum()
                    total_in_weight = pd.to_numeric(df_m['Net_Quantity'], errors='coerce').sum()
                    if total_in_weight > 0:
                        avg_density = total_in_cal / total_in_weight
                        waste_cal = waste_net * avg_density

        submitted = st.form_submit_button("💾 記錄完食/剩餘")
        
        if submitted:
            str_date = record_date.strftime("%Y/%m/%d")
            now_time = datetime.now().strftime("%H:%M:%S")
            timestamp = f"{str_date} {now_time}"
            
            row = [
                str(uuid.uuid4()), timestamp, str_date, now_time, meal_name,
                "WASTE" if waste_net > 0 else "FINISH",
                "剩食", 0, bowl_weight, -waste_net, -waste_cal, 0, 0, 0, "",
                "完食紀錄", finish_time_str
            ]
            try:
                sheet_log.append_row(row)
                st.toast("✅ 完食紀錄已儲存")
                load_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"寫入失敗：{e}")