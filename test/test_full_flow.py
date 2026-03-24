"""
完整审核流程测试
1. 解析规范文档
2. 使用规范审核图片
3. 生成 Markdown 报告
"""

import sys
import json
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.document_parser import document_parser
from src.services.rules_context import rules_context
from src.services.audit_service import audit_service


def main():
    print("=" * 70)
    print("品牌合规审核 - 完整流程")
    print("=" * 70)

    # 1. 解析规范文档
    print("\n[步骤1] 解析规范文档...")
    rules_file = project_root / "data/uploads/PDF/讯飞品牌设计标准.pdf"

    if not rules_file.exists():
        print(f"✗ 规范文件不存在: {rules_file}")
        return

    print(f"  文件: {rules_file}")

    try:
        rules = document_parser.parse_file(str(rules_file))
        brand_id = rules_context.add_rules(rules)
        print(f"✓ 解析成功!")
        print(f"  品牌: {rules.brand_name or '未识别'}")
        print(f"  规范ID: {brand_id}")

        # 显示提取的规范
        if rules.color:
            print(f"\n  【色彩规范】")
            if rules.color.primary:
                print(f"    主色: {rules.color.primary.value} ({rules.color.primary.name})")
            if rules.color.secondary:
                for c in rules.color.secondary:
                    print(f"    辅助色: {c.value} ({c.name})")
            if rules.color.forbidden:
                for c in rules.color.forbidden:
                    print(f"    禁用色: {c.value} - {c.reason or ''}")

        if rules.logo:
            print(f"\n  【Logo规范】")
            print(f"    位置: {rules.logo.position_description}")
            if rules.logo.size_range:
                print(f"    尺寸范围: {rules.logo.size_range.get('min')}% - {rules.logo.size_range.get('max')}%")
            print(f"    安全间距: {rules.logo.safe_margin_px}px")

        if rules.font:
            print(f"\n  【字体规范】")
            if rules.font.allowed:
                print(f"    允许: {', '.join(rules.font.allowed)}")
            if rules.font.forbidden:
                print(f"    禁用: {', '.join(rules.font.forbidden)}")

    except Exception as e:
        print(f"✗ 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 2. 审核图片
    print("\n[步骤2] 审核图片...")

    images = [
        project_root / "data/uploads/20260323-105800.jpg",
        project_root / "data/uploads/20260323-105807.jpg",
    ]

    reports = []

    for i, image_path in enumerate(images, 1):
        if not image_path.exists():
            print(f"✗ 图片不存在: {image_path}")
            continue

        print(f"\n  审核图片 {i}: {image_path.name}")

        try:
            report = audit_service.audit_file(str(image_path), brand_id)
            reports.append({
                "file": image_path.name,
                "report": report
            })

            print(f"  ✓ 审核完成!")
            print(f"    分数: {report.score}")
            print(f"    状态: {report.status.value}")
            print(f"    问题数: {len(report.issues)}")

        except Exception as e:
            print(f"  ✗ 审核失败: {e}")
            import traceback
            traceback.print_exc()

    # 3. 生成报告
    print("\n[步骤3] 生成 Markdown 报告...")

    if not reports:
        print("✗ 没有审核结果，无法生成报告")
        return

    md_content = generate_markdown_report(rules, reports, brand_id)

    # 保存报告
    output_dir = project_root / "data/exports"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"audit_report_{timestamp}.md"

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(md_content)

    print(f"\n✓ 报告已生成: {output_file}")
    print(f"✓ 规范已保存: brand_id={brand_id}")

    # 打印报告内容
    print("\n" + "=" * 70)
    print("审核报告内容")
    print("=" * 70)
    print(md_content)

    # 保存审核历史
    print("\n[步骤4] 保存审核历史...")
    history_dir = project_root / "data" / "audit_history"
    history_dir.mkdir(parents=True, exist_ok=True)

    for r in reports:
        report = r["report"]
        batch_id = f"single_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{Path(r['file']).stem}"

        history_data = {
            "batch_id": batch_id,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brand_name": rules.brand_name or "未命名",
            "file_name": r["file"],
            "file_count": 1,
            "status": report.status.value,
            "score": report.score,
            "report": json.loads(report.to_json())
        }

        history_file = history_dir / f"{batch_id}.json"
        with open(history_file, "w", encoding="utf-8") as f:
            json.dump(history_data, f, ensure_ascii=False, indent=2)

        print(f"  ✓ 已保存: {history_file.name}")

    # 更新历史索引
    index_file = history_dir / "history_index.json"
    history_list = []
    if index_file.exists():
        with open(index_file, "r", encoding="utf-8") as f:
            history_list = json.load(f)

    for r in reports:
        report = r["report"]
        history_list.insert(0, {
            "batch_id": f"single_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{Path(r['file']).stem}",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "brand_name": rules.brand_name or "未命名",
            "file_name": r["file"],
            "file_count": 1,
            "status": report.status.value,
            "score": report.score,
        })

    history_list = history_list[:100]
    with open(index_file, "w", encoding="utf-8") as f:
        json.dump(history_list, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 完成！规范已保留，审核历史已保存。")
    print(f"  规范ID: {brand_id}")
    print(f"  历史记录数: {len(history_list)}")


def generate_markdown_report(rules, reports, brand_id):
    """生成 Markdown 报告"""
    lines = []

    # 标题
    lines.append("# 品牌合规审核报告")
    lines.append("")
    lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"**品牌规范**: {rules.brand_name or '未命名'}")
    lines.append(f"**规范ID**: {brand_id}")
    lines.append("")

    # 品牌规范摘要
    lines.append("## 品牌规范摘要")
    lines.append("")

    if rules.color:
        lines.append("### 色彩规范")
        lines.append("")
        if rules.color.primary:
            lines.append(f"- **主色**: `{rules.color.primary.value}` ({rules.color.primary.name})")
        if rules.color.secondary:
            colors = ", ".join(f"`{c.value}` ({c.name})" for c in rules.color.secondary)
            lines.append(f"- **辅助色**: {colors}")
        if rules.color.forbidden:
            colors = ", ".join(f"`{c.value}`" for c in rules.color.forbidden)
            lines.append(f"- **禁用色**: {colors}")
        lines.append("")

    if rules.logo:
        lines.append("### Logo规范")
        lines.append("")
        lines.append(f"- **位置**: {rules.logo.position_description}")
        if rules.logo.size_range:
            lines.append(f"- **尺寸范围**: {rules.logo.size_range.get('min')}% - {rules.logo.size_range.get('max')}%")
        lines.append(f"- **安全间距**: {rules.logo.safe_margin_px}px")
        lines.append("")

    if rules.font:
        lines.append("### 字体规范")
        lines.append("")
        if rules.font.allowed:
            lines.append(f"- **允许字体**: {', '.join(rules.font.allowed)}")
        if rules.font.forbidden:
            lines.append(f"- **禁用字体**: {', '.join(rules.font.forbidden)}")
        lines.append("")

    # 审核结果
    lines.append("## 审核结果")
    lines.append("")

    # 汇总表格
    lines.append("| 图片 | 分数 | 状态 | 问题数 |")
    lines.append("|------|------|------|--------|")

    total_score = 0
    for r in reports:
        report = r["report"]
        total_score += report.score
        status_emoji = {"pass": "✅ 通过", "warning": "⚠️ 需修改", "fail": "❌ 不通过"}.get(report.status.value, report.status.value)
        lines.append(f"| {r['file']} | {report.score} | {status_emoji} | {len(report.issues)} |")

    avg_score = total_score / len(reports) if reports else 0
    lines.append("")
    lines.append(f"**平均分数**: {avg_score:.1f}")
    lines.append("")

    # 详细结果
    for i, r in enumerate(reports, 1):
        report = r["report"]
        lines.append(f"### 图片 {i}: {r['file']}")
        lines.append("")
        lines.append(f"**分数**: {report.score}/100")
        lines.append(f"**状态**: {report.status.value}")
        lines.append("")

        # 检测结果
        detection = report.detection
        lines.append("#### 检测结果")
        lines.append("")

        # Logo
        lines.append("**Logo检测**")
        if detection.logo.found:
            lines.append(f"- 检测到: 是")
            lines.append(f"- 位置: {detection.logo.position}")
            lines.append(f"- 尺寸占比: {detection.logo.size_percent}%")
            if detection.logo.position_correct is not None:
                lines.append(f"- 位置正确: {'是' if detection.logo.position_correct else '否'}")
            if detection.logo.size_correct is not None:
                lines.append(f"- 尺寸正确: {'是' if detection.logo.size_correct else '否'}")
        else:
            lines.append("- 检测到: 否")
        lines.append("")

        # 颜色
        if detection.colors:
            lines.append("**颜色检测**")
            for c in detection.colors[:5]:
                lines.append(f"- `{c.hex}` ({c.name}): {c.percent:.1f}%")
            lines.append("")

        # 文字
        if detection.texts:
            lines.append("**文字检测**")
            texts_preview = detection.texts[:10]
            for t in texts_preview:
                lines.append(f"- {t}")
            if len(detection.texts) > 10:
                lines.append(f"- ... 还有 {len(detection.texts) - 10} 条")
            lines.append("")

        # 字体
        if detection.fonts:
            lines.append("**字体检测**")
            for f in detection.fonts[:5]:
                lines.append(f"- {f.font_family} ({f.font_size}) - {'禁用' if f.is_forbidden else '正常'}")
            lines.append("")

        # 问题列表
        if report.issues:
            lines.append("#### 问题列表")
            lines.append("")

            # 按严重程度分组
            critical = [i for i in report.issues if i.severity.value == "critical"]
            major = [i for i in report.issues if i.severity.value == "major"]
            minor = [i for i in report.issues if i.severity.value == "minor"]

            if critical:
                lines.append("**严重问题**")
                for issue in critical:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 💡 建议: {issue.suggestion}")
                lines.append("")

            if major:
                lines.append("**主要问题**")
                for issue in major:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 💡 建议: {issue.suggestion}")
                lines.append("")

            if minor:
                lines.append("**次要问题**")
                for issue in minor:
                    lines.append(f"- {issue.description}")
                    if issue.suggestion:
                        lines.append(f"  - 💡 建议: {issue.suggestion}")
                lines.append("")

        # 总体评价
        if report.summary:
            lines.append("#### 总体评价")
            lines.append("")
            lines.append(report.summary)
            lines.append("")

    # 检查项详情
    lines.append("## 检查项详情")
    lines.append("")

    for i, r in enumerate(reports, 1):
        report = r["report"]
        lines.append(f"### 图片 {i} 检查项")
        lines.append("")

        for check_type, items in report.checks.items():
            type_name = {
                "logo_checks": "Logo检查",
                "color_checks": "色彩检查",
                "font_checks": "字体检查",
                "layout_checks": "排版检查",
                "style_checks": "风格检查"
            }.get(check_type, check_type)

            lines.append(f"**{type_name}**")
            lines.append("")

            for item in items:
                status_icon = {"pass": "✅", "warn": "⚠️", "fail": "❌"}.get(item.status, "❓")
                lines.append(f"- {status_icon} `{item.code}` {item.name}: {item.detail}")

            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()