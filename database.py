# database.py
import sqlite3
import logging
from datetime import datetime
import os # 导入os模块，用于判断文件是否存在

# 配置日志，确保能在控制台看到数据库操作信息
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 定义数据库文件名称
DATABASE_FILE = 'nfts.db'

def init_db(nft_items):
    """
    初始化数据库：
    1. 创建 nft_inventory 表（存储所有盲盒NFT的库存状态）。
    2. 如果 nft_inventory 表是空的，则插入所有 NFT 数据。
    3. 创建 assigned_nfts 表（存储分配历史，避免重复分配）。
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # --- 1. 创建 nft_inventory 表 ---
        # 字段：
        # nft_id: NFT的唯一ID，例如 'ICF001-#01'，作为主键
        # image_url: NFT对应的图片URL
        # name: NFT的名称
        # is_assigned: 分配状态，0表示未分配，1表示已分配
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nft_inventory (
                nft_id TEXT PRIMARY KEY,
                image_url TEXT NOT NULL,
                name TEXT NOT NULL,
                is_assigned INTEGER DEFAULT 0 -- 0:未分配, 1:已分配
            )
        ''')

        # --- 2. 如果 nft_inventory 表是空的，插入所有 NFT 数据 ---
        # 这样确保每次部署或应用启动时，NFT数据只被初始化一次
        cursor.execute("SELECT COUNT(*) FROM nft_inventory")
        if cursor.fetchone()[0] == 0:
            logging.info(f"Populating nft_inventory table with {len(nft_items)} initial NFT items.")
            # 使用 executemany 进行批量插入，提高效率
            data_to_insert = [(item['nft_id'], item['image_url'], item['name']) for item in nft_items]
            cursor.executemany(
                "INSERT INTO nft_inventory (nft_id, image_url, name) VALUES (?, ?, ?)",
                data_to_insert
            )
            conn.commit()
            logging.info("nft_inventory table populated successfully.")
        else:
            logging.info("nft_inventory table already contains data, skipping initial population.")

        # --- 3. 创建 assigned_nfts 表 ---
        # 字段：
        # assignment_id: 分配记录的唯一ID，自增主键
        # nft_id: 分配出去的NFT的ID
        # image_url: 分配出去的NFT的图片URL
        # name: 分配出去的NFT的名称
        # assigned_to_order_id: 分配给哪个Shopify订单ID（设置为UNIQUE，确保一个订单只分配一次）
        # assigned_to_customer_email: 分配给哪个客户的邮箱
        # assigned_at: 分配时间，默认为当前时间
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS assigned_nfts (
                assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                nft_id TEXT NOT NULL,
                image_url TEXT,
                name TEXT,
                assigned_to_order_id TEXT NOT NULL UNIQUE, -- 确保一个订单ID只分配一个NFT
                assigned_to_customer_email TEXT,
                assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        logging.info("Database schema initialized successfully (nft_inventory and assigned_nfts tables).")
    except sqlite3.Error as e:
        logging.error(f"FATAL: Database initialization error: {e}", exc_info=True)
        # 在这里可以考虑sys.exit(1)如果数据库无法初始化，应用就不能正常工作
    finally:
        if conn:
            conn.close()

def get_unassigned_nft():
    """
    随机选择一个“未分配”的NFT，并立即将其状态更新为“已分配”。
    这个操作在数据库层面是原子的，可以处理一定程度的并发请求。
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()

        # 开始一个事务，确保原子性
        # 使用 BEGIN IMMEDIATE 或 BEGIN EXCLUSIVE 以在多进程环境中获取更强的锁定
        # 对于Render的Gunicorn多worker（多个Python进程）环境，SQLite文件锁可能会遇到竞争条件
        # 但是对于盲盒这种每次只修改少量数据且允许轻微并发冲突的场景，通常可以接受
        # 如果追求严格的并发安全，需要迁移到更健壮的数据库如PostgreSQL
        conn.execute("BEGIN IMMEDIATE")

        # 1. 随机选择一个未分配的NFT
        cursor.execute("SELECT nft_id, image_url, name FROM nft_inventory WHERE is_assigned = 0 ORDER BY RANDOM() LIMIT 1")
        nft = cursor.fetchone()

        if nft:
            nft_id, image_url, name = nft
            # 2. 立即将选中的NFT标记为已分配
            cursor.execute("UPDATE nft_inventory SET is_assigned = 1 WHERE nft_id = ?", (nft_id,))
            conn.commit() # 提交事务，释放锁
            logging.info(f"Successfully assigned and marked NFT {nft_id} as assigned.")
            return {'nft_id': nft_id, 'image_url': image_url, 'name': name}
        else:
            logging.warning("No unassigned NFTs left in inventory.")
            conn.rollback() # 如果没有找到NFT，回滚事务
            return None
    except sqlite3.Error as e:
        logging.error(f"Error getting and assigning NFT from inventory: {e}", exc_info=True)
        if conn:
            conn.rollback() # 出现错误时回滚事务
        return None
    finally:
        if conn:
            conn.close()

def record_assignment(nft_id, image_url, name, order_id, customer_email):
    """
    记录NFT分配的历史到 assigned_nfts 表。
    此函数在成功更新Shopify订单后调用。
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        # 尝试插入记录，如果 order_id 已经存在（UNIQUE约束），则会引发IntegrityError
        cursor.execute(
            "INSERT INTO assigned_nfts (nft_id, image_url, name, assigned_to_order_id, assigned_to_customer_email) VALUES (?, ?, ?, ?, ?)",
            (nft_id, image_url, name, order_id, customer_email)
        )
        conn.commit()
        logging.info(f"Recorded assignment in DB: NFT {nft_id} to Order {order_id} ({customer_email})")
        return True
    except sqlite3.IntegrityError:
        logging.warning(f"Assignment record for Order ID {order_id} already exists. Skipping recording.")
        return False # 订单已分配过，不重复记录
    except sqlite3.Error as e:
        logging.error(f"Error recording assignment history: {e}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

def check_order_assigned(order_id):
    """
    检查给定订单ID是否已经分配过NFT。
    用于防止重复处理Webhook事件。
    """
    conn = None
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM assigned_nfts WHERE assigned_to_order_id = ?", (order_id,))
        return cursor.fetchone()[0] > 0
    except sqlite3.Error as e:
        logging.error(f"Error checking order assignment status: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()