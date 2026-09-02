"""预置目的地示例数据（兜底）。

小红书不可用时的兜底素材，刻意精简——每类只留核心几条、去掉 pros/cons/tips 等细节，
明确区别于实时抓取的丰富数据。前端会标注「本次使用兜底数据」。
后续接入真实抓取 / 搜索 API 时，只需替换 research 节点的数据来源，保持字段结构不变。
"""

DESTINATIONS = {
    "东京": {
        "hotels": [
            {"name": "新宿王子大饭店", "price": "约 800 元/晚", "rating": "4.3", "location": "新宿"},
            {"name": "东京站丸之内酒店", "price": "约 1200 元/晚", "rating": "4.6", "location": "东京站"},
        ],
        "attractions": [
            {"name": "新宿御苑", "area": "新宿", "note": "都市绿洲，赏樱名所"},
            {"name": "浅草寺", "area": "浅草", "note": "东京最古寺庙，雷门打卡"},
            {"name": "涩谷 SKY", "area": "涩谷", "note": "高空观景台，俯瞰东京"},
        ],
        "food": [
            {"name": "寿司", "category": "日料", "note": "筑地/银座一带品质佳"},
            {"name": "一兰拉面", "category": "拉面", "note": "24 小时，单人隔间"},
            {"name": "居酒屋", "category": "日料", "note": "新宿、涩谷周边集中"},
        ],
        "transport": [
            {"mode": "地铁/私铁", "detail": "购西瓜卡(Suica)或 Pasmo，全城通用"},
            {"mode": "JR 山手线", "detail": "环线串联新宿/涩谷/上野/东京站"},
        ],
    },
    "大阪": {
        "hotels": [
            {"name": "难波东方酒店", "price": "约 700 元/晚", "rating": "4.2", "location": "难波"},
            {"name": "梅田希尔顿大阪", "price": "约 1000 元/晚", "rating": "4.5", "location": "梅田"},
        ],
        "attractions": [
            {"name": "大阪城", "area": "大阪城公园", "note": "标志性天守阁"},
            {"name": "道顿堀", "area": "难波", "note": "美食街，格力高招牌"},
            {"name": "日本环球影城", "area": "樱岛", "note": "主题乐园"},
        ],
        "food": [
            {"name": "章鱼烧", "category": "小吃", "note": "道顿堀名物"},
            {"name": "大阪烧", "category": "小吃", "note": "自己动手或店家代做"},
            {"name": "串炸", "category": "小吃", "note": "新世界一带老店多"},
        ],
        "transport": [
            {"mode": "地铁", "detail": "覆盖主要景点，购 ICOCA 卡"},
            {"mode": "JR 大阪环状线", "detail": "串联大阪城、梅田、环球影城"},
        ],
    },
    "巴黎": {
        "hotels": [
            {"name": "歌剧院区精品酒店", "price": "约 1500 元/晚", "rating": "4.4", "location": "巴黎歌剧院"},
            {"name": "拉丁区民宿", "price": "约 900 元/晚", "rating": "4.3", "location": "拉丁区"},
        ],
        "attractions": [
            {"name": "埃菲尔铁塔", "area": "战神广场", "note": "巴黎地标"},
            {"name": "卢浮宫", "area": "卢浮宫", "note": "世界级博物馆"},
            {"name": "凯旋门", "area": "香榭丽舍", "note": "香街尽头地标"},
        ],
        "food": [
            {"name": "可颂/法棍", "category": "烘焙", "note": "街角面包店最地道"},
            {"name": "法式蜗牛", "category": "法餐", "note": "传统名菜"},
            {"name": "马卡龙", "category": "甜品", "note": "Ladurée、Pierre Hermé"},
        ],
        "transport": [
            {"mode": "地铁", "detail": "RATP 覆盖广，购 Navigo 卡"},
            {"mode": "RER 快线", "detail": "连接机场、凡尔赛等远郊"},
        ],
    },
}
