"""
审核功能集成测试

测试完整的审核流程
"""

import sys
import base64
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_audit_with_local_image():
    """使用本地图片测试审核功能"""
    print("=" * 60)
    print("审核功能集成测试")
    print("=" * 60)

    from src.services.audit_service import audit_service
    from src.services.rules_context import rules_context
    from src.utils.config import settings

    # 检查 API Key
    if not settings.openai_api_key:
        print("✗ API Key 未配置，跳过审核测试")
        print("  请在 .env 文件中配置 OPENAI_API_KEY")
        return False

    # 查找测试图片
    test_images = [
        project_root / "test" / "test_image.png",
        project_root / "test" / "test_image.jpg",
    ]

    # 如果没有测试图片，创建一个简单的测试图片
    test_image_path = None
    for img_path in test_images:
        if img_path.exists():
            test_image_path = img_path
            break

    if test_image_path is None:
        # 创建一个简单的测试图片
        print("创建测试图片...")
        try:
            from PIL import Image, ImageDraw, ImageFont

            # 创建 800x600 的图片
            img = Image.new('RGB', (800, 600), color='#FFFFFF')
            draw = ImageDraw.Draw(img)

            # 画一个蓝色矩形作为 "Logo"
            draw.rectangle([20, 20, 100, 50], fill='#0066CC')

            # 添加一些文字
            draw.text((20, 100), "测试设计稿", fill='#333333')
            draw.text((20, 150), "品牌合规审核测试", fill='#666666')

            test_image_path = project_root / "test" / "test_image.png"
            test_image_path.parent.mkdir(exist_ok=True)
            img.save(test_image_path)
            print(f"✓ 测试图片创建成功: {test_image_path}")
        except Exception as e:
            print(f"✗ 创建测试图片失败: {e}")
            return False

    print(f"\n测试图片: {test_image_path}")

    # 获取规范
    rules_list = rules_context.list_rules()
    print(f"可用规范数量: {len(rules_list)}")

    brand_id = None
    if rules_list:
        brand_id = rules_list[0].get("brand_id")
        print(f"使用规范: {rules_list[0].get('brand_name', '未命名')}")

    # 执行审核
    print("\n正在执行审核（可能需要 30-60 秒）...")
    try:
        report = audit_service.audit_file(str(test_image_path), brand_id)

        print(f"\n审核结果:")
        print(f"  - 分数: {report.score}")
        print(f"  - 状态: {report.status.value}")
        print(f"  - 摘要: {report.summary[:100]}..." if len(report.summary) > 100 else f"  - 摘要: {report.summary}")

        # 检测结果
        detection = report.detection
        print(f"\n检测结果:")
        print(f"  - Logo: {'已检测到' if detection.logo.found else '未检测到'}")
        if detection.logo.found:
            print(f"    - 位置: {detection.logo.position}")
            print(f"    - 尺寸: {detection.logo.size_percent}%")

        if detection.colors:
            print(f"  - 颜色: {len(detection.colors)} 种")
            for c in detection.colors[:3]:
                print(f"    - {c.hex} ({c.name}): {c.percent:.1f}%")

        if detection.texts:
            print(f"  - 文字: {len(detection.texts)} 条")
            for t in detection.texts[:3]:
                print(f"    - {t}")

        # 问题列表
        if report.issues:
            print(f"\n问题列表 ({len(report.issues)} 项):")
            for issue in report.issues[:5]:
                print(f"  - [{issue.severity.value}] {issue.description}")
                if issue.suggestion:
                    print(f"    建议: {issue.suggestion}")

        print("\n✓ 审核测试成功!")
        return True

    except Exception as e:
        print(f"\n✗ 审核测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_document_parsing():
    """测试文档解析功能"""
    print("\n" + "=" * 60)
    print("文档解析测试")
    print("=" * 60)

    from src.services.document_parser import document_parser
    from src.utils.config import settings

    if not settings.openai_api_key:
        print("✗ API Key 未配置，跳过文档解析测试")
        return False

    # 查找测试文档
    test_docs = []
    for ext in ["*.pdf", "*.pptx", "*.ppt"]:
        test_docs.extend(project_root.glob(f"**/{ext}"))

    # 排除 .venv 目录
    test_docs = [f for f in test_docs if ".venv" not in str(f)]

    if not test_docs:
        print("未找到测试文档（PDF/PPT/PPTX）")
        print("  如需测试，请在项目目录放置测试文档")
        return True  # 不算失败

    test_doc = test_docs[0]
    print(f"测试文档: {test_doc}")

    try:
        print("正在解析文档（可能需要 30-60 秒）...")
        rules = document_parser.parse_file(str(test_doc))

        print(f"\n解析结果:")
        print(f"  - 品牌: {rules.brand_name}")
        print(f"  - 版本: {rules.version}")

        if rules.color:
            print(f"  - 色彩规范:")
            if rules.color.primary:
                print(f"    - 主色: {rules.color.primary.value}")
            if rules.color.secondary:
                print(f"    - 辅助色: {len(rules.color.secondary)} 种")

        if rules.logo:
            print(f"  - Logo规范:")
            print(f"    - 位置: {rules.logo.position_description}")
            print(f"    - 尺寸范围: {rules.logo.size_range}")

        print("\n✓ 文档解析测试成功!")
        return True

    except Exception as e:
        print(f"\n✗ 文档解析测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_integration_tests():
    """运行集成测试"""
    print("\n" + "=" * 60)
    print("品牌合规审核平台 - 集成测试")
    print("=" * 60 + "\n")

    results = []

    results.append(("审核功能", test_audit_with_local_image()))
    results.append(("文档解析", test_document_parsing()))

    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ 通过" if passed else "✗ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False

    print()
    return all_passed


if __name__ == "__main__":
    run_integration_tests()