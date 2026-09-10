# 分层 SVG 与局部修改

将“读材料 → 核对官方素材 → 选择清楚的图示 → 排文字与连线 → 看图修改”作为同一条链路。图的可编辑源是 `scene.json` 和独立素材；SVG、PNG、PDF 是交付物，不是让模型猜测结构的扁平截图。

## 实际支持什么

| 工作 | 实现 | 检查边界 |
|---|---|---|
| 阅读与规划 | research harness 每轮带完整来源文本、已读页图、设计与工具结果；固定请求 `gpt-5.6-sol` | 服务端自报身份核验，不证明远端实际权重 |
| 官方素材 | `official-brand` 目录查询 → 注册 ID → 固定官方资源下载 → 校验哈希 | 当前是六品牌人工核验目录，不是全网品牌搜索 |
| 透明素材 | 官方 SVG/PNG 保留颜色、比例；目录裁切仅移除外围产品说明 | 品牌不生图重画、不自动去底；复杂照片不宣称语义分割 |
| 精确表达 | 独立文字、公式、路径、端口、图形与本地 SVG 素材 | 几何 QA 不判断业务事实 |
| 同义同形 | `symbol_registry` + `concept_bindings` 约束同一概念使用同一素材/形状 | 验证声明一致性，不自动证明符号含义正确；不禁止合理分支配色 |
| 局部修改 | `base_sha256`、允许修改的 ID、深度合并样式、不可变对象哈希、可重放补丁 | 改完必须重新渲染和复核，不沿用旧审图结论 |

## 官方来源与自动导入

以下命令不调用语言模型。查询在本地目录执行；导入才下载一个已核验的固定 URL，并需要明确允许联网。

```bash
python -m demo_core.scene_editor search-brand 抖音
python -m demo_core.scene_editor import-brand official-douyin \
  --output demo/output/brand-assets --allow-network
```

目录包含 Qwen2.5-Omni、腾讯混元、Gemini、Bilibili、YouTube、抖音。来源链接见 `demo_core/official_assets.py`，每份下载旁保留 `provenance.json`、原始文件、渲染文件和预览。来源资源变化导致校验失败时，停止并人工复核目录；不猜新 URL，也不偷偷换成生成图。

目录区分中国抖音标识和 TikTok 国际版字标；Gemini 是品牌标识，具体模型版本仍由独立文字表达。源文件是素材原件，允许的矩形/视窗裁切和安全格式转换会单独记录。官网来源不等于任意使用许可：商标与品牌使用规范仍属原权利人，代码的 MIT 许可不授予商标权。

研究入口开启 `--allow-reference-search` 后，模型可用 `search_assets` 的 `provider: "official-brand"` 查目录，再按返回 ID `import_asset`，无需人工下载上传。Commons 仍是另一个具备开放许可元数据校验的 provider；不混淆二者的权利依据。研究入口的授权上下文包含素材预览；标准业务 Demo 的 Commons 像素仍只在本地处理。

目录没有的品牌，可由用户提供原始文件与来源记录，通过 `--asset-manifest` 登记。PDF/AI 中复杂原稿的准确提取仍需外部矢量工具和人工视觉核验；本工具不宣称已自动识别任意 PDF 中的品牌。

## 一个可直接运行的局部编辑例子

```bash
python -m demo_core.scene_editor inspect examples/scoped_edit/before.scene.json
python -m demo_core.scene_editor edit examples/scoped_edit/before.scene.json \
  --patch examples/scoped_edit/edit.patch.json --output demo/output/scoped-edit
```

示例为独立创作的合成符号，无真实品牌或内部业务资料。运行会保留 `before.scene.json`、`figure.scene.json`、`edit.patch.json`、`edit.receipt.json` 与原始素材，并导出 `figure.svg`、`figure.png`、`figure.pdf` 和 `manifest.json`。输出目录必须是新目录。输出包可移动后重放：

```bash
python -m demo_core.scene_editor edit demo/output/scoped-edit/before.scene.json \
  --patch demo/output/scoped-edit/edit.patch.json --output demo/output/scoped-edit-replay
```

自己的图应把素材放在同目录 `assets/` 下，scene 使用相对路径。用 `inspect` 获取当前 SHA-256 与元素 ID，补丁例子如下；替换占位哈希后运行。

```json
{
  "version": 1,
  "base_sha256": "COPY_CURRENT_SCENE_SHA256_HERE",
  "scope": {"editable_ids": ["source_mark", "source_label"]},
  "updates": [
    {"id": "source_mark", "source": "assets/new-mark.svg"},
    {"id": "source_label", "text": "New source"}
  ]
}
```

不在范围内的节点、连线和画布不能被这个补丁改动；版本不匹配、重复/未知 ID、越界素材路径和非有限坐标会被拒绝。样式只改一个字段时，其余样式保留。回执记录的是数据对象完整性，不是“整张图语义正确”的证明。

需要模型理解口语化修改时，使用研究入口的 `--initial-scene`、显式 `--asset-manifest`、`--editable-id` 和 `--narrow-revision`；它仍需要 API 授权与当前图的复核。上面的本地编辑命令完全离线，不会额外调用模型或重跑性能实验。

## SVG 安全与保真

支持路径、基本图形、渐变、clipPath、受约束的样式和内嵌栅格。每次嵌入会重新命名资源 ID，避免不同 logo 的渐变/裁切 ID 互相覆盖；保留 viewBox 与比例。模型看的是从实际原件生成的 PNG 预览，渲染用安全 SVG 图形；二者对应同一份素材。

不接受脚本、事件处理器、外部资源、DTD/实体、foreignObject 或任意网络图片。复杂过滤器、mask、use、嵌套 SVG 等不在当前有限子集中：保留原件，并显式使用经过视觉核验的 PNG 导出，不能静默改图。最终 SVG 的文字与连线仍可独立编辑；导入 PNG fallback 的品牌内部像素不能伪称原生矢量。

机器检查通过后仍保留 `human_approval: pending`。公开发布前应另外检查图稿权限和运行日志；不要把私有来源、逐轮响应或整个运行目录直接推到公开仓库。
