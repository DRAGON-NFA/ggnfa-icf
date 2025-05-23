import os
import sqlite3
import random
import logging
from flask import Flask, request, jsonify

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

DATABASE = 'nft_inventory.db'

# 数据库初始化和 NFT 库存填充
def init_db():
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # 创建 nft_inventory 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nft_inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT NOT NULL UNIQUE,
                is_assigned INTEGER DEFAULT 0
            )
        ''')
        logging.info("nft_inventory table created or already exists.")

        # 创建 assigned_nfts 表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assigned_nfts (
                order_id TEXT UNIQUE NOT NULL,
                customer_email TEXT NOT NULL,
                assigned_nft TEXT NOT NULL
            )
        ''')
        logging.info("assigned_nfts table created or already exists.")

        # 检查 nft_inventory 是否为空，如果为空则填充数据
        cursor.execute("SELECT COUNT(*) FROM nft_inventory")
        if cursor.fetchone()[0] == 0:
            logging.info("Populating nft_inventory table with 6000 initial NFT items.")
            nfts = [f"NFT_Item_{i:04d}" for i in range(1, 6001)]
            cursor.executemany("INSERT INTO nft_inventory (item_name) VALUES (?)", [(nft,) for nft in nfts])
            conn.commit()
            logging.info("nft_inventory table populated successfully.")
        else:
            logging.info("nft_inventory table already populated.")

        conn.close()
        logging.info("Database schema initialized successfully (nft_inventory and assigned_nfts tables).")
    except Exception as e:
        logging.error(f"Error initializing database: {e}")

# 在应用程序启动时调用数据库初始化
with app.app_context():
    init_db()

def assign_nft_to_order(order_id, customer_email):
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    try:
        # 尝试从已分配的 NFT 中查找（如果订单已处理过）
        cursor.execute("SELECT assigned_nft FROM assigned_nfts WHERE order_id = ?", (order_id,))
        existing_assignment = cursor.fetchone()
        if existing_assignment:
            logging.info(f"Order {order_id} already has an assigned NFT: {existing_assignment[0]}. Skipping re-assignment.")
            conn.close()
            return existing_assignment[0]

        # 查找一个未分配的 NFT
        cursor.execute("SELECT item_name FROM nft_inventory WHERE is_assigned = 0 LIMIT 1")
        available_nft = cursor.fetchone()

        if available_nft:
            nft_name = available_nft[0]
            # 将 NFT 标记为已分配
            cursor.execute("UPDATE nft_inventory SET is_assigned = 1 WHERE item_name = ?", (nft_name,))
            # 记录分配到 assigned_nfts 表
            cursor.execute("INSERT INTO assigned_nfts (order_id, customer_email, assigned_nft) VALUES (?, ?, ?)",
                           (order_id, customer_email, nft_name))
            conn.commit()
            logging.info(f"Assigned NFT '{nft_name}' to order '{order_id}' for '{customer_email}'.")
            return nft_name
        else:
            logging.warning("No unassigned NFTs available in inventory.")
            return None
    except sqlite3.Error as e:
        logging.error(f"Database error during NFT assignment: {e}")
        conn.rollback() # 回滚事务以防出错
        return None
    finally:
        conn.close()

@app.route('/')
def home():
    logging.info("Received GET request to /")
    # 您的其他主页逻辑（如果需要）
    return "NFT Inventory Service is running!"

@app.route('/webhooks/orders/paid', methods=['POST'])
def orders_paid_webhook():
    logging.info("Received POST request to /webhooks/orders/paid (Shopify Order Paid Webhook).")

    # --- 开始调试代码 ---
    raw_data = request.get_data(as_text=True)
    logging.info(f"Raw incoming data: {raw_data!r}")  # 使用 !r 显示原始字符串表示

    if not raw_data:
        logging.error("Error: Received empty request body.")
        return jsonify({"status": "error", "message": "Received empty request body"}), 400

    try:
        # 尝试使用 request.get_json() 解析 JSON
        # 如果 Content-Type 不正确，或者请求体不是有效 JSON，它会抛出错误
        data = request.get_json()
        logging.info(f"Parsed JSON data: {data}")
        
        if data is None: # 如果 get_json() 返回 None 但没有抛出错误，可能是空 JSON
            logging.error("Error: Parsed JSON data is None. Request body might be empty JSON or not parseable.")
            return jsonify({"status": "error", "message": "Invalid JSON: parsed data is None"}), 400

    except Exception as e:
        logging.error(f"Error parsing JSON with request.get_json(): {e}")
        # 如果 Flask 的自动解析失败，尝试手动解析原始数据
        try:
            data = json.loads(raw_data)
            logging.info(f"Manually parsed JSON data: {data}")
        except Exception as manual_e:
            logging.error(f"Manual JSON parsing also failed: {manual_e}")
            # 如果手动解析也失败，返回详细错误信息
            return jsonify({"status": "error", "message": f"Failed to decode JSON object. Original error: {e}, Manual parse error: {manual_e}"}), 400
        # 如果手动解析成功，继续执行 webhook 逻辑，但仍然记录原始错误
        logging.warning("Proceeding with manually parsed JSON after initial parsing failure.")

    # --- 调试代码结束 ---

    # 您的现有业务逻辑
    try:
        order_id = data.get('id')
        customer_email = data.get('email')
        current_total_price = float(data.get('current_total_price'))
        currency = data.get('currency')
        order_name = data.get('name') # 例如： "#1018NFA"

        if not all([order_id, customer_email, current_total_price, currency, order_name]):
            logging.error(f"Missing essential data in webhook: Order ID={order_id}, Email={customer_email}, Price={current_total_price}, Currency={currency}, Order Name={order_name}")
            return jsonify({"status": "error", "message": "Missing essential order data"}), 400

        logging.info(f"Webhook data received for order {order_id}: Email={customer_email}, Total Price={current_total_price} {currency}, Order Name={order_name}")

        # 如果您有其他逻辑（例如调用第三方 API），请在此处添加
        # 例如：
        # if your_condition:
        #     response = requests.post("your_another_api_endpoint", json=data)
        #     if response.status_code != 200:
        #         logging.error(f"Failed to send data to another API: {response.text}")
        #         return jsonify({"status": "error", "message": "Failed to process external API"}), 500

        # 分配 NFT
        assigned_nft = assign_nft_to_order(order_id, customer_email)

        if assigned_nft:
            logging.info(f"Successfully processed order {order_id}. Assigned NFT: {assigned_nft}")
            return jsonify({
                "status": "success",
                "message": "Webhook processed successfully",
                "order_id": order_id,
                "assigned_nft": assigned_nft
            }), 200
        else:
            logging.error(f"Failed to assign NFT for order {order_id}. No NFTs available or database error.")
            return jsonify({"status": "error", "message": "Failed to assign NFT"}), 500

    except AttributeError as e:
        # 当 data 不是字典（例如是 int 或 None）时会发生
        logging.error(f"AttributeError in webhook processing: {e}. Data received was not a dictionary as expected.")
        return jsonify({"status": "error", "message": f"Invalid data format received: {e}"}), 400
    except KeyError as e:
        # 当尝试访问不存在的键时会发生
        logging.error(f"KeyError in webhook processing: Missing data key: {e}")
        return jsonify({"status": "error", "message": f"Missing expected data key: {e}"}), 400
    except ValueError as e:
        # 当 float() 转换失败时会发生
        logging.error(f"ValueError in webhook processing: Data type conversion error: {e}")
        return jsonify({"status": "error", "message": f"Data type conversion error: {e}"}), 400
    except Exception as e:
        # 捕获所有其他意外错误
        logging.error(f"Unexpected error during webhook processing: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"An unexpected error occurred: {e}"}), 500

if __name__ == '__main__':
    # 在生产环境中，Gunicorn 会处理端口，所以这个 if 块通常只用于本地测试
    # 在 Render 上，Gunicorn 会通过命令行参数设置端口
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
