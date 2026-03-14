# -*- coding: utf-8 -*-

"""Explicit intent: whether the user question is related to HR handbook."""
from __future__ import annotations

import re

HR_KEYWORDS = [
    "考勤", "请假", "休假", "年假", "病假", "事假", "调休",
    "薪酬", "工资", "薪资", "奖金", "报销",
    "入职", "离职", "试用", "转正", "合同",
    "制度", "手册", "规定", "政策", "流程",
    "福利", "保险", "晋升", "绩效",
    "加班", "出差", "报销", "审批",
    "员工", "人事", "人力资源", "HR",
]


def is_hr_handbook_related(question: str) -> bool:
    """
    Return True if the question appears related to HR handbook / company policy,
    so that we should run retrieval. Otherwise False -> answer "我不知道" without retrieval.
    """
    q = (question or "").strip()
    if not q or len(q) < 2:
        return False
    q_lower = q.lower()
    for kw in HR_KEYWORDS:
        if kw in q:
            return True
    for term in ["leave", "vacation", "salary", "policy", "handbook", "hr", "attendance", "benefit"]:
        if term in q_lower:
            return True
    if len(q) >= 8 and (re.search(r"[？?]", q) or q.endswith(("吗", "呢", "什么", "怎么", "如何"))):
        return True
    if len(q) < 15:
        return False
    return True
