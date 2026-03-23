import asyncio
import json
import logging
from pathlib import Path

from analyzer.extractor import extract
from classifier.rule_classifier import classify_by_extension
from config.schema import AiConfig, ScanResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个文件分类助手。根据文件名、内容摘要和元数据，提供 1-3 个可能的分类方案，按置信度从高到低排列。

分类体系（category → subcategory）：
- 文档 → 合同 / 协议 / 报告 / 简历 / 论文 / 笔记 / 电子书 / 表格 / 演示文稿 / 发票 / 收据 / 说明书 / 其他
- 图片 → 照片 / 截图 / 设计素材 / 扫描件 / 证件 / 其他
- 视频 → 录屏 / 课程 / 影视 / 个人视频 / 会议录像 / 其他
- 音频 → 音乐 / 播客 / 录音 / 有声书 / 其他
- 代码 → 项目 / 脚本 / 配置 / 数据文件 / 其他
- 压缩包 → 安装包 / 项目包 / 资料包 / 备份 / 其他
- 其他 → 其他

返回规则：
- 分类明确（confidence ≥ 0.85）：返回 1 个选项
- 有歧义（如文件名模糊、内容不明）：返回 2-3 个选项
- suggested_name 使用中文，不含扩展名和特殊字符，最长 30 字，要具体而非泛化
- reasoning 简明说明分类依据（文件名特征、内容关键词等）

只返回 JSON 数组，不要加 markdown 代码块：
[
  {"category":"文档","subcategory":"合同","suggested_name":"腾讯NDA保密协议","confidence":0.95,"reasoning":"文件名含NDA，内容包含保密条款"},
  {"category":"文档","subcategory":"协议","suggested_name":"腾讯合作协议","confidence":0.65,"reasoning":"也可能是合作协议类文件"}
]"""


def _build_user_message(file: ScanResult, extraction: dict) -> str:
    return json.dumps({
        "file_name": Path(file.path).name,
        "extension": file.extension,
        "size_mb": round(file.size_bytes / 1024 / 1024, 2),
        "modified_date": file.modified_time[:10],
        "content_summary": extraction.get("summary_text", "")[:1500],
        "metadata": extraction.get("metadata", {}),
    }, ensure_ascii=False)


def _parse_response(text: str) -> list[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    result = json.loads(text.strip())
    if isinstance(result, dict):
        result = [result]
    return result[:3]  # cap at 3 options


async def _classify_one(client, model: str, file: ScanResult, extraction: dict) -> dict:
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _build_user_message(file, extraction)},
                ],
                temperature=0.2,
                timeout=30,
            )
            content = response.choices[0].message.content or ""
            options = _parse_response(content)
            return {
                "path": file.path,
                "options": [
                    {
                        "category": opt.get("category", "其他"),
                        "subcategory": opt.get("subcategory", "其他"),
                        "suggested_name": opt.get("suggested_name", Path(file.path).stem),
                        "confidence": float(opt.get("confidence", 0.7)),
                        "reasoning": opt.get("reasoning", ""),
                    }
                    for opt in options
                ],
                "classification_method": "ai",
                "selected_option_index": 0,
            }
        except Exception as e:
            if attempt == 2:
                logger.warning("AI classification failed for %s after 3 attempts: %s", file.path, e)
                break
            await asyncio.sleep(2 ** attempt)

    # Fallback to extension-based rule classifier
    fallback = classify_by_extension(file.path)
    return {
        "path": file.path,
        "options": [{
            "category": fallback["category"],
            "subcategory": fallback["subcategory"],
            "suggested_name": fallback["suggested_name"],
            "confidence": fallback["confidence"],
            "reasoning": "按扩展名规则分类（AI 不可用）",
        }],
        "classification_method": "fallback_extension",
        "selected_option_index": 0,
    }


async def classify_files(files: list[ScanResult], ai_config: AiConfig) -> list[dict]:
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=ai_config.api_key,
            base_url=ai_config.base_url,
        )
    except Exception as e:
        logger.error("Failed to init OpenAI client: %s", e)
        results = []
        for f in files:
            fallback = classify_by_extension(f.path)
            results.append({
                "path": f.path,
                "options": [{
                    "category": fallback["category"],
                    "subcategory": fallback["subcategory"],
                    "suggested_name": fallback["suggested_name"],
                    "confidence": fallback["confidence"],
                    "reasoning": "按扩展名规则分类（AI 初始化失败）",
                }],
                "classification_method": "fallback_extension",
                "selected_option_index": 0,
            })
        return results

    extractions = [extract(Path(f.path)) for f in files]

    # Up to 20 concurrent AI calls
    sem = asyncio.Semaphore(20)

    async def limited(file: ScanResult, extraction: dict) -> dict:
        async with sem:
            return await _classify_one(client, ai_config.model, file, extraction)

    results = await asyncio.gather(*[limited(f, e) for f, e in zip(files, extractions)])
    return list(results)


async def test_connection(ai_config: AiConfig) -> dict:
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=ai_config.api_key, base_url=ai_config.base_url)
        response = await client.chat.completions.create(
            model=ai_config.model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=5,
            timeout=10,
        )
        return {"ok": True, "message": f"连接成功，模型：{response.model}"}
    except Exception as e:
        return {"ok": False, "message": str(e)}
