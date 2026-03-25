# 品牌合规审核平台

## GitHub Actions 自动打包说明

### 方法一：通过 Tag 触发（推荐）

```bash
# 创建并推送 tag
git tag v1.0.0
git push origin v1.0.0
```

GitHub Actions 会自动：
1. 在 Windows/Linux/macOS 三个平台上打包
2. 创建 Release 页面
3. 上传三个平台的安装包

### 方法二：手动触发

1. 打开 GitHub 仓库页面
2. 点击 **Actions** 标签
3. 选择 **Build and Release** 工作流
4. 点击 **Run workflow**
5. 输入版本号，点击绿色按钮运行

### 下载安装包

打包完成后：
1. 进入仓库的 **Releases** 页面
2. 下载对应平台的压缩包

### 平台使用说明

| 平台 | 文件名 | 使用方法 |
|------|--------|----------|
| Windows | `品牌合规审核平台-Windows.zip` | 解压后运行 `品牌合规审核平台.exe` |
| Linux | `品牌合规审核平台-Linux.zip` | 解压后运行 `./启动程序.sh` |
| macOS | `品牌合规审核平台-macOS.zip` | 解压后双击 `.app` 文件 |

### 注意事项

1. **首次运行需要配置 API Key**
   - DeepSeek API：用于解析品牌规范文档
   - Doubao API：用于图片审核

2. **macOS 特别说明**
   - 首次打开可能提示"无法验证开发者"
   - 解决方法：系统偏好设置 → 安全性与隐私 → 点击"仍要打开"
   - 或在终端运行：`xattr -cr 品牌合规审核平台.app`

3. **数据持久化**
   - 所有数据保存在程序目录下的 `data/` 文件夹
   - 升级时请备份 `data/` 文件夹