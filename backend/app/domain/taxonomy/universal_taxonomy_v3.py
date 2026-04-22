"""Broad fixed three-level taxonomy for general knowledge-base documents."""

from __future__ import annotations

import os
import re
from typing import Any


TAXONOMY_VERSION = "taxonomy_v3"


DOMAIN_GROUPS: dict[str, dict[str, list[str]]] = {
    "办公文档": {
        "综合办公": ["通用办公材料", "通知公告", "申请审批", "工作汇报", "办公模板"],
        "会议纪要": ["会议纪要", "会议议程", "会议材料", "会议决议", "行动项跟踪"],
        "制度流程": ["管理制度", "流程规范", "操作规程", "内控流程", "制度汇编"],
        "行政后勤": ["行政通知", "资产登记", "办公用品", "后勤安排", "用印申请"],
    },
    "财务税务": {
        "综合财务": ["通用财务材料", "财务说明", "财务制度", "财务台账", "财务附件"],
        "出纳结算": ["出纳管理", "银行流水", "现金日记账", "资金调拨", "账户管理"],
        "报销付款": ["费用报销", "付款审批", "差旅报销", "借款申请", "付款凭证"],
        "账务报表": ["财务月报", "资产负债表", "利润表", "现金流量表", "审计报告"],
        "预算成本": ["预算申请", "成本分析", "费用预算", "预算执行", "成本台账"],
        "税务管理": ["税务申报", "发票台账", "纳税资料", "税务筹划", "税务审查"],
    },
    "人力组织": {
        "综合人事": ["通用人事材料", "人事通知", "组织架构", "员工手册", "人事台账"],
        "招聘录用": ["招聘需求", "Offer审批", "面试记录", "岗位说明", "录用材料"],
        "员工关系": ["入职材料", "离职办理", "劳动合同", "员工证明", "关系处理"],
        "绩效薪酬": ["绩效考核", "薪酬方案", "奖金方案", "调薪审批", "考勤记录"],
        "培训发展": ["培训计划", "课程材料", "学习地图", "培训记录", "人才盘点"],
    },
    "法务合规": {
        "综合法务": ["通用法务材料", "法务说明", "合规材料", "法律资料", "法务台账"],
        "合同协议": ["标准合同", "销售合同", "采购合同", "合作协议", "补充协议"],
        "审查意见": ["法务审查", "法律意见", "风险提示", "合同审查", "争议处理"],
        "知识产权": ["知识产权", "专利资料", "商标资料", "著作权资料", "授权许可"],
        "授权资质": ["授权文件", "资质证明", "委托书", "证照资料", "用印授权"],
        "隐私合规": ["隐私条款", "数据合规", "安全承诺", "监管要求", "合规制度"],
    },
    "产品项目": {
        "综合项目": ["通用项目材料", "项目说明", "项目附件", "项目资料", "综合项目文档"],
        "需求规划": ["需求文档", "版本规划", "产品路线图", "需求清单", "功能说明"],
        "项目管理": ["项目计划", "项目周报", "项目复盘", "风险清单", "里程碑计划"],
        "交付验收": ["验收清单", "交付文档", "验收报告", "上线计划", "发布说明"],
        "用户研究": ["用户调研", "访谈记录", "问卷分析", "用户画像", "可用性测试"],
    },
    "研发技术": {
        "综合技术": ["通用技术文档", "技术资料", "技术说明", "研发资料", "技术附件"],
        "架构设计": ["架构设计", "系统设计", "模块设计", "技术选型", "方案设计"],
        "接口文档": ["接口文档", "API文档", "协议说明", "参数说明", "集成文档"],
        "开发规范": ["开发手册", "编码规范", "工程规范", "代码说明", "开发指南"],
        "测试质量": ["测试用例", "测试计划", "缺陷报告", "质量报告", "验收测试"],
        "技术方案": ["技术方案", "实现方案", "迁移方案", "性能优化", "技术调研"],
    },
    "运维安全": {
        "综合运维": ["通用运维材料", "运维资料", "运维说明", "安全资料", "运维附件"],
        "运维体系": ["运维手册", "运行手册", "部署手册", "操作手册", "值班手册"],
        "监控告警": ["巡检记录", "监控报表", "告警规则", "容量报告", "健康检查"],
        "故障应急": ["故障复盘", "应急预案", "应急演练", "事故报告", "恢复方案"],
        "安全治理": ["安全规范", "安全策略", "漏洞报告", "权限管理", "安全基线"],
        "变更资产": ["变更记录", "变更申请", "资产台账", "配置清单", "发布变更"],
    },
    "数据分析": {
        "综合分析": ["通用分析材料", "分析资料", "数据说明", "分析附件", "数据材料"],
        "经营分析": ["经营复盘", "经营月报", "经营看板", "业务分析", "增长分析"],
        "专题分析": ["分析报告", "专题报告", "趋势分析", "归因分析", "实验分析"],
        "报表看板": ["数据周报", "报表说明", "看板说明", "指标报表", "统计报表"],
        "数据治理": ["指标口径", "数据字典", "建模方案", "数据质量", "元数据说明"],
    },
    "销售商务": {
        "综合销售": ["通用销售材料", "销售资料", "商务材料", "销售附件", "商务说明"],
        "售前方案": ["销售方案", "解决方案", "售前材料", "客户方案", "方案报价"],
        "报价投标": ["商务报价", "投标应答", "标书材料", "询价回复", "报价清单"],
        "客户合同": ["销售合同", "客户协议", "续约材料", "回款资料", "客户订单"],
        "客户跟进": ["拜访记录", "客户纪要", "跟进记录", "商机记录", "客户需求"],
    },
    "市场品牌": {
        "综合市场": ["通用市场材料", "市场资料", "品牌材料", "市场附件", "营销说明"],
        "市场策划": ["市场方案", "营销计划", "传播方案", "增长方案", "渠道方案"],
        "活动运营": ["活动策划", "活动执行", "活动复盘", "会务材料", "物料清单"],
        "品牌管理": ["品牌规范", "视觉规范", "品牌手册", "商标素材", "品牌资产"],
        "内容营销": ["推广素材", "内容计划", "文案素材", "媒体稿件", "投放素材"],
        "竞品研究": ["竞品分析", "竞品资料", "市场调研", "对标分析", "行业观察"],
    },
    "客户服务": {
        "综合服务": ["通用服务材料", "服务资料", "客服材料", "服务附件", "客户说明"],
        "服务体系": ["服务手册", "SLA协议", "服务流程", "客服话术", "支持指南"],
        "工单运营": ["工单周报", "工单月报", "工单分析", "问题清单", "处理记录"],
        "客户反馈": ["客户反馈", "满意度调查", "用户建议", "体验反馈", "回访记录"],
        "投诉处理": ["投诉记录", "投诉处理", "升级记录", "客诉分析", "赔付说明"],
    },
    "图书资料": {
        "综合图书": ["综合书籍", "通用图书资料", "图书目录", "阅读资料", "参考书籍"],
        "计算机图书": ["编程语言书籍", "计算机基础教材", "软件工程书籍", "数据库书籍", "人工智能书籍", "网络安全书籍"],
        "经济金融图书": ["金融历史书籍", "经济学书籍", "投资理财书籍", "会计财务书籍", "商业管理书籍"],
        "社科图书": ["社会学书籍", "历史文化书籍", "政治法律书籍", "心理学书籍", "教育学书籍"],
        "科技产业图书": ["互联网产业书籍", "科技史书籍", "产业分析书籍", "企业传记书籍", "创新创业书籍"],
    },
    "研究分析": {
        "综合研究": ["通用研究材料", "研究资料", "研究综述", "参考资料", "研究附件"],
        "行业研究": ["行业报告", "市场规模报告", "竞争格局报告", "趋势报告", "产业链报告"],
        "学术论文": ["学术论文", "会议论文", "期刊论文", "学位论文", "实验论文"],
        "政策研究": ["政策解读", "政策汇编", "监管分析", "法规研究", "政策建议"],
        "咨询报告": ["咨询报告", "调研报告", "诊断报告", "战略报告", "可研报告"],
    },
}


FALLBACK_PATHS = {
    ("办公文档", "综合办公", "通用办公材料"),
    ("财务税务", "综合财务", "通用财务材料"),
    ("人力组织", "综合人事", "通用人事材料"),
    ("法务合规", "综合法务", "通用法务材料"),
    ("产品项目", "综合项目", "通用项目材料"),
    ("研发技术", "综合技术", "通用技术文档"),
    ("运维安全", "综合运维", "通用运维材料"),
    ("数据分析", "综合分析", "通用分析材料"),
    ("销售商务", "综合销售", "通用销售材料"),
    ("市场品牌", "综合市场", "通用市场材料"),
    ("客户服务", "综合服务", "通用服务材料"),
    ("图书资料", "综合图书", "综合书籍"),
    ("研究分析", "综合研究", "通用研究材料"),
}


DOMAIN_SLUGS = {
    "办公文档": "office",
    "财务税务": "finance_tax",
    "人力组织": "hr",
    "法务合规": "legal",
    "产品项目": "product_project",
    "研发技术": "engineering",
    "运维安全": "ops_security",
    "数据分析": "data",
    "销售商务": "sales",
    "市场品牌": "marketing",
    "客户服务": "customer_service",
    "图书资料": "books",
    "研究分析": "research",
}


GROUP_SLUGS = {
    ("办公文档", "综合办公"): "general",
    ("图书资料", "计算机图书"): "computer",
    ("研发技术", "综合技术"): "general",
}


LEAF_SLUGS = {
    ("办公文档", "综合办公", "通用办公材料"): "general_material",
    ("图书资料", "计算机图书", "编程语言书籍"): "programming_language",
    ("研发技术", "综合技术", "通用技术文档"): "general_technical_document",
}


KEYWORD_OVERRIDES = {
    ("图书资料", "计算机图书", "编程语言书籍"): ["Rust", "C++", "cpp", "modern-cpp", "Python", "CUDA", "NVIDIA", "Programming", "tutorial", "编程", "教程", "实战"],
    ("图书资料", "计算机图书", "计算机基础教材"): ["操作系统", "计算机组成", "算法", "网络", "导论", "教材"],
    ("图书资料", "计算机图书", "软件工程书籍"): ["重构", "设计模式", "代码质量", "软件工程"],
    ("图书资料", "科技产业图书", "互联网产业书籍"): ["互联网", "科技公司", "产业", "浪潮之巅"],
    ("图书资料", "经济金融图书", "金融历史书籍"): ["金融史", "货币", "银行", "经济史"],
    ("图书资料", "社科图书", "社会学书籍"): ["社会", "分层", "社会学", "阶层"],
    ("财务税务", "报销付款", "付款审批"): ["付款", "审批", "付款单"],
    ("财务税务", "出纳结算", "出纳管理"): ["出纳", "资金", "现金", "银行"],
}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.lower()).strip("_")
    if slug:
        return slug
    codepoints = "_".join(f"{ord(char):x}" for char in value)
    return f"u_{codepoints}"


def _label_id(domain: str, group: str, label: str) -> str:
    override = LEAF_SLUGS.get((domain, group, label))
    domain_slug = DOMAIN_SLUGS.get(domain, _slugify(domain))
    group_slug = GROUP_SLUGS.get((domain, group), _slugify(group))
    leaf_slug = override or _slugify(label)
    return f"{domain_slug}.{group_slug}.{leaf_slug}"


def _build_catalog() -> list[dict[str, Any]]:
    labels = []
    used_ids: set[str] = set()
    for domain, groups in DOMAIN_GROUPS.items():
        for group, leaf_names in groups.items():
            for leaf_name in leaf_names:
                path = (domain, group, leaf_name)
                label_id = _label_id(domain, group, leaf_name)
                if label_id in used_ids:
                    raise ValueError(f"Duplicate taxonomy_v3 label id: {label_id} for {format_path({'path': path})}")
                used_ids.add(label_id)
                keywords = [domain, group, leaf_name, *KEYWORD_OVERRIDES.get(path, [])]
                labels.append(
                    {
                        "id": label_id,
                        "path": [domain, group, leaf_name],
                        "label": leaf_name,
                        "description": f"{domain}/{group}/{leaf_name}",
                        "aliases": [],
                        "keywords": list(dict.fromkeys(keywords)),
                        "fallback": path in FALLBACK_PATHS,
                        "taxonomy_version": TAXONOMY_VERSION,
                    }
                )
    return labels


CATALOG = _build_catalog()
_BY_ID = {label["id"]: label for label in CATALOG}
_BY_PATH = {tuple(label["path"]): label for label in CATALOG}
_DOMAINS = list(DOMAIN_GROUPS.keys())


def _copy_label(label: dict[str, Any] | None) -> dict[str, Any] | None:
    if label is None:
        return None
    copied = dict(label)
    copied["path"] = list(label.get("path") or [])
    copied["aliases"] = list(label.get("aliases") or [])
    copied["keywords"] = list(label.get("keywords") or [])
    return copied


def get_all_labels() -> list[dict[str, Any]]:
    return [_copy_label(label) for label in CATALOG]


def get_domain_options() -> list[str]:
    return list(_DOMAINS)


def get_label_by_id(label_id: str) -> dict[str, Any] | None:
    return _copy_label(_BY_ID.get(str(label_id or "")))


def get_label_by_path(path: list[str] | tuple[str, str, str] | str) -> dict[str, Any] | None:
    if isinstance(path, str):
        parts = [part.strip() for part in path.replace(">", "/").split("/") if part.strip()]
    else:
        parts = [str(part or "").strip() for part in path]
    if len(parts) != 3:
        return None
    return _copy_label(_BY_PATH.get(tuple(parts)))


def get_labels_by_domain(domain: str) -> list[dict[str, Any]]:
    normalized = str(domain or "").strip()
    return [_copy_label(label) for label in CATALOG if label["path"][0] == normalized]


def get_domain_fallback(domain: str) -> dict[str, Any] | None:
    normalized = str(domain or "").strip()
    for label in CATALOG:
        if label["path"][0] == normalized and label.get("fallback"):
            return _copy_label(label)
    return None


def format_path(label: dict[str, Any]) -> str:
    return "/".join(str(part) for part in label.get("path") or [])


def infer_domain_from_filename(filename: str, file_type: str = "") -> str:
    suffix = file_type or os.path.splitext(str(filename or ""))[1]
    text = f"{filename or ''} {suffix or ''}".lower()

    if any(word in text for word in ["付款", "报销", "发票", "出纳", "预算", "财务", "税务"]):
        return "财务税务"
    if any(word in text for word in ["招聘", "offer", "入职", "离职", "绩效", "薪酬"]):
        return "人力组织"
    if any(word in text for word in ["合同", "协议", "法务", "合规", "授权"]):
        return "法务合规"
    if any(word in text for word in ["rust", "c++", "python", "编程", "教程", "导论", "重构", "z-library", "书籍", "金融史", "社会分层"]):
        return "图书资料"
    if any(word in text for word in ["研究", "论文", "政策", "咨询", "调研"]):
        return "研究分析"
    if any(word in text for word in ["接口", "api", "架构", "开发", "代码"]):
        return "研发技术"
    if any(word in text for word in ["运维", "故障", "巡检", "安全", "变更"]):
        return "运维安全"
    if any(word in text for word in ["销售", "报价", "投标", "客户"]):
        return "销售商务"
    return "办公文档"
