import os
import sqlite3
import random
import logging
from flask import Flask, request, jsonify
import json
import requests # 用于外部 API 调用，此库是必需的

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 初始化 Flask 应用
app = Flask(__name__)

# 数据库文件路径
DATABASE = 'nft_inventory.db'

# NFT 数据定义
# 这是一个示例，您可以在这里定义您的 NFT 盲盒内容
# 确保这里的图片 URL 是可公开访问的 CDN 链接
# 如果您有实际的 NFT 图片，请替换这些 URL
NFT_ITEMS_DATA = []
NUM_MAIN_SERIES = 200 # 主系列数量
NUM_SUB_SERIES_PER_MAIN = 30 # 每个主系列包含的子系列数量

# 生成 NFT 项目数据
# 每个 NFT 都有一个唯一的 ID 和名称
# 并且有一个对应的图片 URL
# 这里的图片 URL 是示例，您需要替换为您的实际图片链接
# 确保图片数量与 NUM_MAIN_SERIES 匹配
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
    # ... 您可以添加更多图片 URL，确保至少有 NUM_MAIN_SERIES 数量的图片
    # 如果您的实际图片数量少于 NUM_MAIN_SERIES，请重复使用或调整逻辑
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
    conn = None # 初始化 conn 为 None
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # 创建 nft_inventory 表
        # item_name 存储 NFT 的唯一标识符（例如 NFT_001_01）
        # is_assigned 标记该 NFT 是否已被分配 (0: 未分配, 1: 已分配)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nft_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL UNIQUE, -- 存储 NFT_ITEMS_DATA 中的 id
                item_name TEXT NOT NULL,      -- 存储 NFT_ITEMS_DATA 中的 name
                image_url TEXT NOT NULL,      -- 存储 NFT_ITEMS_DATA 中的 image_url
                is_assigned INTEGER DEFAULT 0
            )
        ''')
        logging.info("nft_inventory table created or already exists.")

        # 创建 assigned_nfts 表
        # 记录哪个订单 ID 获得了哪个 NFT
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assigned_nfts (
                order_id TEXT UNIQUE NOT NULL,    -- Shopify 订单的唯一 ID
                customer_email TEXT NOT NULL,     -- 购买者的邮箱
                assigned_nft_id TEXT NOT NULL,    -- 分配的 NFT 的 item_id
                assigned_nft_name TEXT NOT NULL,  -- 分配的 NFT 的 item_name
                assigned_nft_image TEXT NOT NULL, -- 分配的 NFT 的 image_url
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        logging.info("assigned_nfts table created or already exists.")

        # 检查 nft_inventory 是否为空，如果为空则填充数据
        cursor.execute("SELECT COUNT(*) FROM nft_inventory")
        if cursor.fetchone()[0] == 0:
            logging.info(f"Populating nft_inventory table with {len(NFT_ITEMS_DATA)} initial NFT items.")
            # 使用 NFT_ITEMS_DATA 填充
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

# 在应用程序启动时调用数据库初始化
with app.app_context():
    init_db()

# 分配 NFT 给订单的函数
def assign_nft_to_order(order_id, customer_email):
    conn = None
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # 1. 检查订单是否已经分配过 NFT
        cursor.execute("SELECT assigned_nft_id, assigned_nft_name, assigned_nft_image FROM assigned_nfts WHERE order_id = ?", (order_id,))
        existing_assignment = cursor.fetchone()
        if existing_assignment:
            logging.info(f"Order {order_id} already has an assigned NFT: {existing_assignment[0]}. Skipping re-assignment.")
            return {
                "id": existing_assignment[0],
                "name": existing_assignment[1],
                "image_url": existing_assignment[2]
            }

        # 2. 查找一个未分配的 NFT
        cursor.execute("SELECT item_id, item_name, image_url FROM nft_inventory WHERE is_assigned = 0 ORDER BY RANDOM() LIMIT 1")
        available_nft = cursor.fetchone()

        if available_nft:
            nft_id, nft_name, nft_image_url = available_nft
            
            # 3. 将 NFT 标记为已分配
            cursor.execute("UPDATE nft_inventory SET is_assigned = 1 WHERE item_id = ?", (nft_id,))
            
            # 4. 记录分配到 assigned_nfts 表
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
            conn.rollback() # 回滚事务以防出错
        return None
    except Exception as e:
        logging.error(f"Unexpected error during NFT assignment for order {order_id}: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()

# 主页路由，用于健康检查或简单信息展示
@app.route('/')
def home():
    logging.info("Received GET request to /")
    return "NFT Inventory Service is running! Webhook endpoint: /webhooks/orders/paid"

# Shopify 订单支付 Webhook 接收端点
@app.route('/webhooks/orders/paid', methods=['POST'])
def orders_paid_webhook():
    logging.info("Received POST request to /webhooks/orders/paid (Shopify Order Paid Webhook).")

    # 获取原始请求体数据
    raw_data = request.get_data(as_text=True)
    logging.info(f"Raw incoming data: {raw_data!r}")

    # 检查请求体是否为空
    if not raw_data:
        logging.error("Error: Received empty request body.")
        return jsonify({"status": "error", "message": "Received empty request body"}), 400

    # 尝试手动解析原始数据为 JSON
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

    # 业务逻辑处理
    try:
        # 从解析后的 JSON 数据中提取关键信息
        order_id = data.get('id')
        # Shopify 订单的联系邮箱可能在 'contact_email' 或 'email' 字段
        customer_email = data.get('contact_email') or data.get('email')
        current_total_price = float(data.get('current_total_price', 0.0))
        currency = data.get('currency')
        order_name = data.get('name')

        # 检查关键数据是否存在
        if not all([order_id, customer_email, currency, order_name]):
            logging.error(f"Missing essential data in webhook: Order ID={order_id}, Email={customer_email}, Currency={currency}, Order Name={order_name}")
            return jsonify({"status": "error", "message": "Missing essential order data"}), 400

        logging.info(f"Webhook data received for order {order_id}: Email={customer_email}, Total Price={current_total_price} {currency}, Order Name={order_name}")

        # 分配 NFT
        assigned_nft_info = assign_nft_to_order(order_id, customer_email)

        if assigned_nft_info:
            logging.info(f"Successfully processed order {order_id}. Assigned NFT: {assigned_nft_info['name']} (ID: {assigned_nft_info['id']})")

            # **** Shopify Admin API 调用部分 - 已取消注释 ****
            SHOPIFY_STORE_URL = os.environ.get("SHOPIFY_STORE_URL")
            SHOPIFY_ADMIN_API_ACCESS_TOKEN = os.environ.get("SHOPIFY_ADMIN_API_ACCESS_TOKEN")

            if SHOPIFY_STORE_URL and SHOPIFY_ADMIN_API_ACCESS_TOKEN:
                # 注意 Shopify API 版本，这里使用 2024-07，您可以根据实际情况调整
                order_update_url = f"https://{SHOPIFY_STORE_URL}/admin/api/2024-07/orders/{order_id}.json"
                headers = {
                    "X-Shopify-Access-Token": SHOPIFY_ADMIN_API_ACCESS_TOKEN,
                    "Content-Type": "application/json"
                }
                # 构建要更新的 note_attributes
                # 注意：这会替换订单中现有的 note_attributes。
                # 如果您需要追加而不是替换，逻辑会更复杂，需要先获取现有 attributes。
                updated_note_attributes = [
                    {"name": "Assigned_NFT_ID", "value": assigned_nft_info['id']},
                    {"name": "Assigned_NFT_Name", "value": assigned_nft_info['name']},
                    {"name": "Assigned_NFT_Image_URL", "value": assigned_nft_info['image_url']} # 确保这里是正确的键名
                ]
                update_payload = {
                    "order": {
                        "id": order_id,
                        "note_attributes": updated_note_attributes
                    }
                }
                try:
                    response = requests.put(order_update_url, headers=headers, json=update_payload)
                    response.raise_for_status() # 如果状态码不是 2xx，则抛出 HTTPError
                    logging.info(f"Successfully updated Shopify order {order_id} with NFT details.")
                except requests.exceptions.RequestException as req_e:
                    logging.error(f"Failed to update Shopify order {order_id} via Admin API: {req_e}. Response: {response.text if response else 'N/A'}")
            else:
                logging.warning("Shopify Admin API credentials (SHOPIFY_STORE_URL or SHOPIFY_ADMIN_API_ACCESS_TOKEN) not set. Cannot update order note_attributes.")
            # **** Shopify Admin API 调用部分结束 ****

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

