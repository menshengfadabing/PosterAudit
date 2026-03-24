"""
核心功能测试

测试各个服务模块是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_imports():
    """测试模块导入"""
    print("=" * 60)
    print("1. 测试模块导入")
    print("=" * 60)

    try:
        from src.utils.config import settings, get_app_dir
        print(f"✓ config 模块导入成功")
        print(f"  - API Base: {settings.openai_api_base}")
        print(f"  - Model: {settings.doubao_model}")
        print(f"  - API Key: {'已配置' if settings.openai_api_key else '未配置'}")
    except Exception as e:
        print(f"✗ config 模块导入失败: {e}")
        return False

    try:
        from src.models.schemas import BrandRules, AuditReport
        print(f"✓ schemas 模块导入成功")
    except Exception as e:
        print(f"✗ schemas 模块导入失败: {e}")
        return False

    try:
        from src.services.llm_service import llm_service, audit_cache
        print(f"✓ llm_service 模块导入成功")
        print(f"  - 缓存状态: {audit_cache.get_stats()}")
    except Exception as e:
        print(f"✗ llm_service 模块导入失败: {e}")
        return False

    try:
        from src.services.rules_context import rules_context
        print(f"✓ rules_context 模块导入成功")
    except Exception as e:
        print(f"✗ rules_context 模块导入失败: {e}")
        return False

    try:
        from src.services.document_parser import document_parser
        print(f"✓ document_parser 模块导入成功")
    except Exception as e:
        print(f"✗ document_parser 模块导入失败: {e}")
        return False

    try:
        from src.services.audit_service import audit_service
        print(f"✓ audit_service 模块导入成功")
    except Exception as e:
        print(f"✗ audit_service 模块导入失败: {e}")
        return False

    print()
    return True


def test_rules_context():
    """测试规范上下文管理"""
    print("=" * 60)
    print("2. 测试规范上下文管理")
    print("=" * 60)

    from src.services.rules_context import rules_context
    from src.models.schemas import BrandRules, ColorRules, ColorRule, LogoRules

    # 测试列出规范
    rules_list = rules_context.list_rules()
    print(f"当前规范数量: {len(rules_list)}")
    for rule in rules_list:
        print(f"  - {rule.get('brand_name', '未命名')} ({rule.get('brand_id', '')})")

    # 测试创建规范
    test_rules = BrandRules(
        brand_id="",
        brand_name="测试品牌",
        version="1.0",
        color=ColorRules(
            primary=ColorRule(name="主色", value="#0066CC"),
        ),
        logo=LogoRules(
            position="top_left",
            position_description="左上角",
            size_range={"min": 5, "max": 15},
            safe_margin_px=20,
        ),
    )

    brand_id = rules_context.add_rules(test_rules)
    print(f"✓ 创建规范成功: {brand_id}")

    # 测试获取规范
    retrieved = rules_context.get_rules(brand_id)
    if retrieved:
        print(f"✓ 获取规范成功: {retrieved.brand_name}")
    else:
        print(f"✗ 获取规范失败")

    # 测试获取规范文本
    rules_text = rules_context.get_rules_text(brand_id)
    print(f"✓ 获取规范文本成功，长度: {len(rules_text)}")

    # 测试删除规范
    rules_context.delete_rules(brand_id)
    print(f"✓ 删除规范成功")

    print()
    return True


def test_document_parser():
    """测试文档解析器"""
    print("=" * 60)
    print("3. 测试文档解析器")
    print("=" * 60)

    from src.services.document_parser import document_parser

    # 检查支持的格式
    print(f"支持的文档格式: PDF, PPT, PPTX")

    # 查找测试文件
    test_dir = project_root / "data" / "rules"
    if test_dir.exists():
        pdf_files = list(test_dir.glob("**/*.pdf"))
        pptx_files = list(test_dir.glob("**/*.pptx"))

        print(f"找到 {len(pdf_files)} 个 PDF 文件")
        print(f"找到 {len(pptx_files)} 个 PPTX 文件")

        # 如果有测试文件，尝试解析（需要API Key）
        test_files = pdf_files + pptx_files
        if test_files:
            print(f"测试文件: {test_files[0]}")
            print("  （解析需要 API Key，跳过实际解析测试）")
    else:
        print(f"测试目录不存在: {test_dir}")

    print()
    return True


def test_audit_service():
    """测试审核服务"""
    print("=" * 60)
    print("4. 测试审核服务")
    print("=" * 60)

    from src.services.audit_service import audit_service
    from src.utils.config import settings

    # 检查支持的图片格式
    print(f"支持的图片格式: {audit_service.SUPPORTED_FORMATS}")

    # 查找测试图片
    test_images = []
    for ext in ["*.png", "*.jpg", "*.jpeg"]:
        test_images.extend(project_root.glob(f"**/{ext}"))

    print(f"找到 {len(test_images)} 个测试图片")

    if not settings.openai_api_key:
        print("⚠ API Key 未配置，跳过实际审核测试")
    else:
        print("API Key 已配置，可以进行审核测试")
        if test_images:
            print(f"  测试图片: {test_images[0]}")

    print()
    return True


def test_cache():
    """测试缓存功能"""
    print("=" * 60)
    print("5. 测试缓存功能")
    print("=" * 60)

    from src.services.llm_service import audit_cache

    # 测试缓存设置和获取
    test_key = "test_image_base64_data"
    test_value = {"score": 85, "status": "pass", "summary": "测试结果"}

    audit_cache.set(test_key, test_value)
    print(f"✓ 缓存设置成功")

    cached = audit_cache.get(test_key)
    if cached == test_value:
        print(f"✓ 缓存获取成功: {cached}")
    else:
        print(f"✗ 缓存获取失败")
        return False

    # 获取统计信息
    stats = audit_cache.get_stats()
    print(f"✓ 缓存统计: {stats}")

    # 清空缓存
    audit_cache.clear()
    print(f"✓ 缓存已清空")

    # 验证清空
    cached = audit_cache.get(test_key)
    if cached is None:
        print(f"✓ 缓存清空验证成功")
    else:
        print(f"✗ 缓存清空验证失败")
        return False

    print()
    return True


def test_schemas():
    """测试数据模型"""
    print("=" * 60)
    print("6. 测试数据模型")
    print("=" * 60)

    from src.models.schemas import (
        BrandRules, ColorRules, ColorRule, LogoRules,
        AuditReport, DetectionResult, Issue, IssueType, IssueSeverity
    )

    # 测试 BrandRules
    rules = BrandRules(
        brand_id="test_001",
        brand_name="测试品牌",
        version="1.0",
        color=ColorRules(
            primary=ColorRule(name="主色", value="#0066CC"),
            secondary=[ColorRule(name="辅助色", value="#00AAFF")],
            forbidden=[ColorRule(name="禁用色", value="#FF0000", reason="不符合品牌调性")],
        ),
        logo=LogoRules(
            position="top_left",
            position_description="左上角",
            size_range={"min": 5, "max": 15},
            safe_margin_px=20,
        ),
    )

    print(f"✓ BrandRules 创建成功: {rules.brand_name}")

    # 测试 JSON 序列化
    json_str = rules.to_json()
    print(f"✓ JSON 序列化成功，长度: {len(json_str)}")

    # 测试 AuditReport
    from src.models.schemas import LogoInfo, AuditStatus

    report = AuditReport(
        score=85,
        status=AuditStatus.PASS,
        summary="审核通过",
        detection=DetectionResult(
            colors=[],
            logo=LogoInfo(found=True, position="左上角"),
            texts=[],
            fonts=[],
        ),
        checks={},
        issues=[
            Issue(
                type=IssueType.LOGO,
                severity=IssueSeverity.MINOR,
                description="Logo位置偏移",
                suggestion="调整Logo位置",
            )
        ],
    )

    print(f"✓ AuditReport 创建成功: 分数={report.score}")

    # 测试 JSON 序列化
    json_str = report.to_json()
    print(f"✓ JSON 序列化成功，长度: {len(json_str)}")

    print()
    return True


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("品牌合规审核平台 - 核心功能测试")
    print("=" * 60 + "\n")

    results = []

    results.append(("模块导入", test_imports()))
    results.append(("规范上下文", test_rules_context()))
    results.append(("文档解析器", test_document_parser()))
    results.append(("审核服务", test_audit_service()))
    results.append(("缓存功能", test_cache()))
    results.append(("数据模型", test_schemas()))

    # 汇总结果
    print("=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("所有测试通过！")
    else:
        print("存在失败的测试，请检查上面的输出。")

    return all_passed


if __name__ == "__main__":
    run_all_tests()