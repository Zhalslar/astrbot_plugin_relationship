import sqlite3
from decimal import Decimal
from pathlib import Path

from astrbot.api.star import StarTools

AFDIAN_DB: Path = StarTools.get_data_dir("astrbot_plugin_afdian") / "orders.db"

afdian_approve_threshold = 10

def afdian_verify(remark: str) -> bool:
    """根据 remark 精确匹配，返回所有订单的 金额总和, 根据总和判断是否通过审核"""
    if AFDIAN_DB.exists() is False:
        return False
    with sqlite3.connect(AFDIAN_DB) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT total_amount FROM afdian_orders "
            "WHERE remark = ? "
            "ORDER BY create_time DESC",
            (remark,),
        )
        amount_list = [
            int(Decimal(str(row[0]))) if row[0] is not None else 0
            for row in cursor.fetchall()
        ]
        return sum(amount_list) >= afdian_approve_threshold


# 后续拓展
