"""SQLite -> PostgreSQL 数据迁移脚本"""
import sqlite3
import json
import sys
from datetime import datetime

# PostgreSQL 连接
try:
    import psycopg2
except ImportError:
    print("请先安装 psycopg2: pip install psycopg2-binary")
    sys.exit(1)

SQLITE_PATH = "/home/ubuntu/travel-planner/deploy/data/trips.db"
PG_DSN = "postgresql://travel:travel2026@localhost:5432/travel_planner"

def migrate():
    # 连接 SQLite
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # 连接 PostgreSQL
    pg_conn = psycopg2.connect(PG_DSN)
    pg_cur = pg_conn.cursor()

    # 创建表（SQLAlchemy 的 create_all 会在后端启动时自动执行，这里手动建）
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS trips (
            id SERIAL PRIMARY KEY,
            user_input TEXT NOT NULL,
            preferences JSON NOT NULL DEFAULT '{}',
            research JSON NOT NULL DEFAULT '{}',
            itinerary TEXT NOT NULL DEFAULT '',
            usage JSON,
            transit JSON,
            transit_error TEXT NOT NULL DEFAULT '',
            hotels JSON,
            parent_id INTEGER,
            chat_history JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS user_profile (
            id SERIAL PRIMARY KEY,
            departure_city VARCHAR(64) DEFAULT '',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS xhs_note_cache (
            id SERIAL PRIMARY KEY,
            destination VARCHAR(64) NOT NULL,
            url TEXT NOT NULL,
            title VARCHAR(255) DEFAULT '',
            summary TEXT DEFAULT '',
            cover TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(destination, url)
        )
    """)
    
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS ctrip_city_cache (
            id SERIAL PRIMARY KEY,
            city_name VARCHAR(64) UNIQUE NOT NULL,
            city_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    pg_cur.execute("""
        CREATE TABLE IF NOT EXISTS ctrip_hotel_cache (
            id SERIAL PRIMARY KEY,
            destination VARCHAR(64) NOT NULL,
            keyword VARCHAR(128) NOT NULL,
            hotel_name VARCHAR(255) NOT NULL,
            price INTEGER DEFAULT 0,
            rating INTEGER DEFAULT 0,
            location VARCHAR(255) DEFAULT '',
            image TEXT DEFAULT '',
            url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(destination, keyword, hotel_name)
        )
    """)
    pg_conn.commit()
    print("表创建完成")

    # 迁移 trips
    rows = sqlite_cur.execute("SELECT * FROM trips").fetchall()
    for row in rows:
        pg_cur.execute(
            """INSERT INTO trips (id, user_input, preferences, research, itinerary, usage, transit, transit_error, hotels, parent_id, chat_history, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (id) DO NOTHING""",
            (
                row["id"],
                row["user_input"],
                json.dumps(json.loads(row["preferences"])) if row["preferences"] else '{}',
                json.dumps(json.loads(row["research"])) if row["research"] else '{}',
                row["itinerary"],
                json.dumps(json.loads(row["usage"])) if row["usage"] else None,
                json.dumps(json.loads(row["transit"])) if row["transit"] else None,
                row["transit_error"],
                json.dumps(json.loads(row["hotels"])) if row["hotels"] else None,
                row["parent_id"],
                json.dumps(json.loads(row["chat_history"])) if row["chat_history"] else None,
                row["created_at"],
            ),
        )
    print(f"trips: 迁移 {len(rows)} 条")

    # 迁移 user_profile
    rows = sqlite_cur.execute("SELECT * FROM user_profile").fetchall()
    for row in rows:
        pg_cur.execute(
            "INSERT INTO user_profile (id, departure_city, updated_at) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
            (row["id"], row["departure_city"], row["updated_at"]),
        )
    print(f"user_profile: 迁移 {len(rows)} 条")

    # 迁移 xhs_note_cache
    rows = sqlite_cur.execute("SELECT * FROM xhs_note_cache").fetchall()
    for row in rows:
        pg_cur.execute(
            """INSERT INTO xhs_note_cache (id, destination, url, title, summary, cover, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (destination, url) DO NOTHING""",
            (row["id"], row["destination"], row["url"], row["title"], row["summary"], row["cover"], row["created_at"]),
        )
    print(f"xhs_note_cache: 迁移 {len(rows)} 条")

    # 迁移 ctrip_city_cache
    rows = sqlite_cur.execute("SELECT * FROM ctrip_city_cache").fetchall()
    for row in rows:
        pg_cur.execute(
            "INSERT INTO ctrip_city_cache (id, city_name, city_id, created_at) VALUES (%s, %s, %s, %s) ON CONFLICT (city_name) DO NOTHING",
            (row["id"], row["city_name"], row["city_id"], row["created_at"]),
        )
    print(f"ctrip_city_cache: 迁移 {len(rows)} 条")

    # 迁移 ctrip_hotel_cache
    rows = sqlite_cur.execute("SELECT * FROM ctrip_hotel_cache").fetchall()
    for row in rows:
        pg_cur.execute(
            """INSERT INTO ctrip_hotel_cache (id, destination, keyword, hotel_name, price, rating, location, image, url, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (destination, keyword, hotel_name) DO NOTHING""",
            (row["id"], row["destination"], row["keyword"], row["hotel_name"], row["price"], row["rating"], row["location"], row["image"], row["url"], row["created_at"]),
        )
    print(f"ctrip_hotel_cache: 迁移 {len(rows)} 条")

    # 重置序列（让后续 INSERT 的 id 从最大值 +1 开始）
    for table in ["trips", "user_profile", "xhs_note_cache", "ctrip_city_cache", "ctrip_hotel_cache"]:
        pg_cur.execute(f"SELECT setval('{table}_id_seq', (SELECT COALESCE(MAX(id), 1) FROM {table}))")
    
    pg_conn.commit()
    print("\n迁移完成！序列已重置。")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()
