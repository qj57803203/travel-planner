"""导入携程城市 ID 到 CtripCityCache 表。

用法：
    cd backend
    python import_city_ids.py [json_file_path]

默认读取 app/tools/cityIdList.json，写入 SQLite 的 ctrip_city_cache 表。
幂等操作：已存在的城市会更新 city_id，新城市直接插入。
"""

import json
import sys
from pathlib import Path

# 确保能导入 app 模块
sys.path.insert(0, str(Path(__file__).parent))

from app.database import SessionLocal, engine, Base
from app.models import CtripCityCache


def extract_cities(data: dict) -> list[tuple[str, int]]:
    """从携程城市 JSON 中提取 (cityName, cityId) 列表。"""
    cities = []

    # 国内城市
    inland = data.get("data", {}).get("inlandCityModel", {}).get("cityModelGroups", [])
    for group in inland:
        for region in group.get("regionModels", []):
            display = region.get("displayCityModel", {})
            basic = region.get("basicCityModel", {})
            name = display.get("cityName", "").strip()
            city_id = basic.get("cityId")
            if name and city_id:
                cities.append((name, city_id))

    # 海外城市
    global_ = data.get("data", {}).get("globalCityModel", {}).get("cityModelGroups", [])
    for group in global_:
        for region in group.get("regionModels", []):
            display = region.get("displayCityModel", {})
            basic = region.get("basicCityModel", {})
            name = display.get("cityName", "").strip()
            city_id = basic.get("cityId")
            if name and city_id:
                cities.append((name, city_id))

    return cities


def import_cities(json_path: str, clear_first: bool = True) -> None:
    """读取 JSON 文件并导入城市数据到数据库。

    Args:
        json_path: JSON 文件路径
        clear_first: 是否先清空表再导入（默认 True，避免重复数据冲突）
    """
    # 确保表存在
    Base.metadata.create_all(bind=engine, tables=[CtripCityCache.__table__])

    # 读取 JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cities = extract_cities(data)
    if not cities:
        print("未提取到任何城市数据，请检查 JSON 文件格式")
        return

    # 去重：同一个城市名只保留最后一个 city_id
    city_dict: dict[str, int] = {}
    for city_name, city_id in cities:
        city_dict[city_name] = city_id

    print(f"从 JSON 中提取到 {len(cities)} 条记录，去重后 {len(city_dict)} 个城市")

    with SessionLocal() as db:
        # 先清空表（避免旧数据冲突）
        if clear_first:
            db.query(CtripCityCache).delete()
            db.commit()
            print("已清空旧数据")

        # 批量插入
        added = 0
        for city_name, city_id in city_dict.items():
            if clear_first:
                # 清空模式下直接插入
                db.add(CtripCityCache(city_name=city_name, city_id=city_id))
                added += 1
            else:
                # 非清空模式：先查再改/加
                existing = db.query(CtripCityCache).filter(
                    CtripCityCache.city_name == city_name
                ).first()
                if existing:
                    if existing.city_id != city_id:
                        existing.city_id = city_id
                else:
                    db.add(CtripCityCache(city_name=city_name, city_id=city_id))
                    added += 1

        db.commit()

    print(f"导入完成：{'新增' if clear_first else '写入'} {added} 个城市")


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else str(
        Path(__file__).parent / "app" / "tools" / "cityIdList.json"
    )
    print(f"读取文件：{json_path}")
    import_cities(json_path)
