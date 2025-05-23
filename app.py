import os
import sqlite3
import random
import logging
from flask import Flask, request, jsonify
import json
import requests

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 初始化 Flask 应用
app = Flask(__name__)

# 数据库文件路径
DATABASE = 'nft_inventory.db'

# NFT 数据定义
NFT_ITEMS_DATA = []
NUM_MAIN_SERIES = 200 # 主系列数量
NUM_SUB_SERIES_PER_MAIN = 30 # 每个主系列包含的子系列数量

# 生成 NFT 项目数据
TEST_IMAGE_URLS = [
    "https://images.unsplash.com/photo-1549497554-e0b49f5c2f5d?w=400&h=400&fit=crop&q=80", # 抽象艺术
    "https://images.unsplash.com/photo-1579783902674-fb825d52288b?w=400&h=400&fit=crop&q=80", # 几何抽象
    "https://images.unsplash.com/photo-1550684376-effd6e810750?w=400&h=400&fit=crop&q=80", # 城市夜景
    "https://images.unsplash.com/photo-1517420704952-f96c561b365f?w=400&h=400&fit=crop&q=80", # 自然风景
    "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=400&h=400&fit=crop&q=80", # 海滩日出
    "https://images.unsplash.com/photo-1506744038136-465a60a35c83?w=400&h=400&fit=crop&q=80", # 山脉
    "https://images.unsplash.com/photo-1518779578993-ec3579df2682?w=400&h=400&fit=crop&q=80", # 抽象纹理
    "https://images.unsplash.com/photo-1508921912186-1d1a45fa5342?w=400&h=400&fit=crop&q=80", # 极简主义
    "https://images.unsplash.com/photo-1516542076529-1bbd85698717?w=400&h=400&fit=crop&q=80", # 科技感
    "https://images.unsplash.com/photo-1518066000714-cdcd82531e89?w=400&h=400&fit=crop&q=80"  # 赛博朋克
]

# 填充 NFT_ITEMS_DATA 列表
for i in range(NUM_MAIN_SERIES):
    base_image_url = TEST_IMAGE_URLS[i % len(TEST_IMAGE_URLS)] # 循环使用图片 URL
    for j in range(NUM_SUB_SERIES_PER_MAIN):
        nft_id = f"NFT_{i+1:03d}_{j+1:02d}" # 例如：NFT_001_01, NFT_001_02
        nft_name = f"盲盒系列 {i+1} 子系列 {j+1}"
        nft_image = base_image_url # 暂时使用主系列的图片
        NFT_ITEMS_DATA.append({
            "id": nft_id,
            "name": nft_name,
            "image_url": nft_image
        })
logging.info(f"Generated {len(NFT_ITEMS_DATA)} unique NFT items.")


# 数据库初始化函数
def init_db():
    conn = None
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nft_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL UNIQUE,
                item_name TEXT NOT NULL,
                image_url TEXT NOT NULL,
                is_assigned INTEGER DEFAULT 0
            )
        ''')
        logging.info("nft_inventory table created or already exists.")

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assigned_nfts (
                order_id TEXT UNIQUE NOT NULL,
                customer_email TEXT NOT NULL,
                assigned_nft_id TEXT NOT NULL,
                assigned_nft_name TEXT NOT NULL,
                assigned_nft_image TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logging.info("assigned_nfts table created or already exists.")

        cursor.execute("SELECT COUNT(*) FROM nft_inventory")
        if cursor.fetchone()[0] == 0:
            logging.info(f"Populating nft_inventory table with {len(NFT_ITEMS_DATA)} initial NFT items.")
            data_to_insert = [(item['id'], item['name'], item['image_url']) for item in NFT_ITEMS_DATA]
            cursor.executemany("INSERT INTO nft_inventory (item_id, item_name, image_url) VALUES (?, ?, ?)", data_to_insert)
            conn.commit()
            logging.info("nft_inventory table populated successfully.")
        else:
            logging.info("nft_inventory table already populated.")

        logging.info("Database schema initialized successfully (nft_inventory and assigned_nfts tables).")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()

with app.app_context():
    init_db()

def assign_nft_to_order(order_id, customer_email):
    conn = None
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        cursor.execute("SELECT assigned_nft_id, assigned_nft_name, assigned_nft_image FROM assigned_nfts WHERE order_id = ?", (order_id,))
        existing_assignment = cursor.fetchone()
        if existing_assignment:
            logging.info(f"Order {order_id} already has an assigned NFT: {existing_assignment[0]}. Skipping re-assignment.")
            return {
                "id": existing_assignment[0],
                "name": existing_assignment[1],
                "image_url": existing_assignment[2]
            }

        cursor.execute("SELECT item_id, item_name, image_url FROM nft_inventory WHERE is_assigned = 0 ORDER BY RANDOM() LIMIT 1")
        available_nft = cursor.fetchone()

        if available_nft:
            nft_id, nft_name, nft_image_url = available_nft
            
            cursor.execute("UPDATE nft_inventory SET is_assigned = 1 WHERE item_id = ?", (nft_id,))
            
            cursor.execute("INSERT INTO assigned_nfts (order_id, customer_email, assigned_nft_id, assigned_nft_name, assigned_nft_image) VALUES (?, ?, ?, ?, ?)",
                           (order_id, customer_email, nft_id, nft_name, nft_image_url))
            conn.commit()
            logging.info(f"Assigned NFT '{nft_name}' (ID: {nft_id}) to order '{order_id}' for '{customer_email}'.")
            
            return {
                "id": nft_id,
                "name": nft_name,
                "image_url": nft_image_url
            }
        else:
            logging.warning("No unassigned NFTs available in inventory.")
            return None
    except sqlite3.Error as e:
        logging.error(f"Database error during NFT assignment for order {order_id}: {e}")
        if conn:
            conn.rollback()
        return None
    except Exception as e:
        logging.error(f"Unexpected error during NFT assignment for order {order_id}: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

@app.route('/')
def home():
    logging.info("Received GET request to /")
    return "NFT Inventory Service is running! Webhook endpoint: /webhooks/orders/paid"

@app.route('/webhooks/orders/paid', methods=['POST'])
def orders_paid_webhook():
    logging.info("Received POST request to /webhooks/orders/paid (Shopify Order Paid Webhook).")

    raw_data = request.get_data(as_text=True)
    logging.info(f"Raw incoming data: {raw_data!r}")

    if not raw_data:
        logging.error("Error: Received empty request body.")
        return jsonify({"status": "error", "message": "Received empty request body"}), 400

    data = None
    try:
        data = json.loads(raw_data)
        logging.info(f"Manually parsed JSON data: {data}")

    except json.JSONDecodeError as e:
        logging.error(f"Failed to decode JSON from raw data: {e}")
        return jsonify({"status": "error", "message": f"Invalid JSON received: {e}"}), 400
    except Exception as e:
        logging.error(f"Unexpected error during manual JSON parsing: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"An unexpected parsing error occurred: {e}"}), 400

    try:
        order_id = data.get('id')
        customer_email = data.get('contact_email') or data.get('email')
        current_total_price = float(data.get('current_total_price', 0.0))
        currency = data.get('currency')
        order_name = data.get('name')

        if not all([order_id, customer_email, currency, order_name]):
            logging.error(f"Missing essential data in webhook: Order ID={order_id}, Email={customer_email}, Currency={currency}, Order Name={order_name}")
            return jsonify({"status": "error", "message": "Missing essential order data"}), 400

        logging.info(f"Webhook data received for order {order_id}: Email={customer_email}, Total Price={current_total_price} {currency}, Order Name={order_name}")

        assigned_nft_info = assign_nft_to_order(order_id, customer_email)

        if assigned_nft_info:
            logging.info(f"Successfully processed order {order_id}. Assigned NFT: {assigned_nft_info['name']} (ID: {assigned_nft_info['id']})")

            SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL")
            SHOPIFY_ADMIN_API_ACCESS_TOKEN = os.environ.get("SHOPIFY_ADMIN_API_ACCESS_TOKEN")

            if SHOPIFY_STORE_URL and SHOPIFY_ADMIN_API_ACCESS_TOKEN:
                headers = {
                    "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_ACCESS_TOKEN,
                    "Content-Type": "application/json"
                }
                
                get_order_url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-07/orders/{order_id}.json"
                existing_note_attributes = []
                try:
                    get_response = requests.get(get_order_url, headers=headers)
                    get_response.raise_for_status()
                    existing_order_data = get_response.json()
                    existing_note_attributes = existing_order_data.get('order', {}).get('note_attributes', [])
                    logging.info(f"Successfully retrieved existing note_attributes for order {order_id}: {existing_note_attributes}")
                except requests.exceptions.RequestException as get_req_e:
                    error_response_text = "N/A"
                    if get_response is not None:
                        try:
                            error_response_text = get_response.text
                            logging.error(f"Shopify GET API Error Status Code: {get_response.status_code}")
                            logging.error(f"Shopify GET API Error Response Body: {error_response_text}")
                        except Exception as inner_e:
                            logging.error(f"Could not get response text from Shopify GET API: {inner_e}")
                    logging.error(f"Failed to retrieve existing note_attributes for Shopify order {order_id}: {get_req_e}. Proceeding with only new attributes.")
                    existing_note_attributes = [] 


                updated_note_attributes = list(existing_note_attributes)
                
                # 检查是否已存在 NFT 属性，如果存在则更新，否则添加
                # 避免重复添加相同的 NFT 属性
                nft_id_key_exists = False
                for attr in updated_note_attributes:
                    if attr.get('name') == "Assigned_NFT_ID":
                        attr['value'] = str(assigned_nft_info['id'])
                        nft_id_key_exists = True
                    if attr.get('name') == "Assigned_NFT_Name":
                        attr['value'] = str(assigned_nft_info['name'])
                    if attr.get('name') == "Assigned_NFT_Image_URL":
                        attr['value'] = str(assigned_nft_info['image_url'])
                
                if not nft_id_key_exists:
                    updated_note_attributes.append({"name": "Assigned_NFT_ID", "value": str(assigned_nft_info['id'])})
                    updated_note_attributes.append({"name": "Assigned_NFT_Name", "value": str(assigned_nft_info['name'])})
                    updated_note_attributes.append({"name": "Assigned_NFT_Image_URL", "value": str(assigned_nft_info['image_url'])})
                
                # 确保所有 note_attribute 的 value 都是字符串类型
                for attr in updated_note_attributes:
                    attr['value'] = str(attr['value'])


                update_payload = {
                    "order": {
                        "id": order_id, # 将 order_id 重新添加回 payload
                        "note_attributes": updated_note_attributes
                    }
                }
                
                logging.info(f"Attempting to update Shopify order {order_id} with payload: {json.dumps(update_payload, ensure_ascii=False)}")
                
                order_update_url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-07/orders/{order_id}.json"
                try:
                    response = requests.put(order_update_url, headers=headers, json=update_payload)
                    response.raise_for_status()
                    logging.info(f"Successfully updated Shopify order {order_id} with NFT details.")
                except requests.exceptions.RequestException as req_e:
                    error_response_text = "N/A"
                    if response is not None:
                        try:
                            error_response_text = response.text
                            logging.error(f"Shopify API Error Status Code: {response.status_code}")
                            logging.error(f"Shopify API Error Response Body: {error_response_text}")
                        except Exception as inner_e:
                            logging.error(f"Could not get response text from Shopify API: {inner_e}")
                    logging.error(f"Failed to update Shopify order {order_id} via Admin API: {req_e}. Full response details in preceding log lines.")
            else:
                logging.warning("Shopify Admin API credentials (SHOPIFY_STORE_URL or SHOPIFY_ADMIN_API_ACCESS_TOKEN) not set. Cannot update order note_attributes.")

            return jsonify({
                "status": "success",
                "message": "Webhook processed successfully",
                "order_id": order_id,
                "assigned_nft": assigned_nft_info
            }), 200
        else:
            logging.error(f"Failed to assign NFT for order {order_id}. No NFTs available or database error.")
            return jsonify({"status": "error", "message": "Failed to assign NFT"}), 500

    except AttributeError as e:
        logging.error(f"AttributeError in webhook processing: {e}. Data received was not a dictionary as expected. Raw data: {raw_data!r}")
        return jsonify({"status": "error", "message": f"Invalid data format received: {e}"}), 400
    except KeyError as e:
        logging.error(f"KeyError in webhook processing: Missing data key: {e}. Raw data: {raw_data!r}")
        return jsonify({"status": "error", "message": f"Missing expected data key: {e}"}), 400
    except ValueError as e:
        logging.error(f"ValueError in webhook processing: Data type conversion error: {e}. Raw data: {raw_data!r}")
        return jsonify({"status": "error", "message": f"Data type conversion error: {e}"}), 400
    except Exception as e:
        logging.error(f"Unexpected error during webhook processing: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500

# 应用程序入口点
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

