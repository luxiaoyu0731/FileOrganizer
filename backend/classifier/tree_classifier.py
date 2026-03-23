"""
tree_classifier.py

Holistic, relationship-aware file classification that produces a dynamic
two-level folder hierarchy with AI-generated folder names.

Algorithm — Two-stage, project-aware
-------------------------------------
Stage 1 — Send ALL filenames + directory paths to AI.  AI identifies
           project groups and returns project names + keyword lists.
           Type-based grouping is auto-detected and retried (max 2×),
           with directory-structure fallback as last resort.
           All files are then assigned locally via multi-signal matching:
             • Filename keyword match (substring ×2, token overlap ×1)
             • Parent directory match (×3.0 weight) — strongest signal
             • Grandparent directory match (×2.0 weight)
             • Score normalised by keyword count (prevents bias)
             • Extension keywords (py, pdf, etc.) auto-filtered
             • score == 0 → dedicated "待分类" group (no fallback pollution)
           After keyword matching, time-clustering rescues uncertain files
           whose mtime is within 7 days of confirmed project files.

Stage 2 — Per project group, up to MAX_S2_SAMPLE representative files
           with content summaries → AI generates sub-categories
           (phases / themes within the project, NOT file types).
           Non-sampled files inherit the first sub-category.

Layer 2 — Content-based fallback for text files still unmatched.
Layer A/B/C — Image classification (co-location / EXIF / Vision AI).

Progress tracking
-----------------
Each classify_tree() call accepts an optional request_id. Progress is
stored in the module-level _progress dict and exposed via get_progress().
"""

import asyncio
import json
import logging
import re
from collections import Counter
from pathlib import Path

from analyzer.extractor import extract
from classifier.embedder import (
    build_embedding_text, embed_texts, compute_centroids,
    assign_to_nearest, cluster_embeddings, get_representative_indices,
)
from config.schema import AiConfig, ScanResult

logger = logging.getLogger(__name__)

MAX_S2_SAMPLE        = 150   # max files per Stage-2 AI call (token budget)
UNCERTAIN_BATCH      = 50    # files per batch in Layer-2 content fallback
TIME_CLUSTER_DAYS    = 7     # time-clustering window (days)
SPLIT_THRESHOLD      = 30    # sub-folders with more files get recursively subdivided
MAX_DEPTH            = 4     # maximum folder nesting depth

# Stage-1 sends ALL filenames (names only, no content) so token cost is low:
# 5000 files × ~35 chars/name ≈ 43K chars ≈ 10K tokens — well within 128K context models.

# Image extensions handled by the dedicated image classification pipeline
_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp',
               '.tiff', '.tif', '.heic', '.heif'}

# File-type groups for adaptive content extraction in Layer-2
_CODE_EXTS  = {'.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.c', '.cpp',
               '.go', '.rs', '.rb', '.php', '.sh'}
_TEXT_EXTS  = {'.txt', '.md', '.markdown', '.rst', '.log'}
_DOC_EXTS   = {'.pdf', '.docx', '.doc', '.pptx', '.ppt'}
_TABLE_EXTS = {'.csv', '.xlsx', '.xls'}

# Filename pattern recognisers (Layer A)
_RE_SCREENSHOT = re.compile(
    r'screenshot|截图|snipaste|capture|screen_?shot|jietu', re.IGNORECASE)
_RE_WECHAT = re.compile(
    r'mmexport|wxid_|wechat|微信图片', re.IGNORECASE)
_RE_PHONE_PHOTO = re.compile(
    r'^(?:IMG|DSC|DCIM|PXL|BURST|PORTRAIT|PHOTO)[-_]?\d', re.IGNORECASE)


# ─── Progress tracking & cancellation ─────────────────────────────────────────

_progress: dict[str, dict] = {}
_cancelled: set[str] = set()  # request_ids that have been cancelled


def get_progress(request_id: str) -> dict:
    return _progress.get(
        request_id,
        {"current": 0, "total": 0, "stage": "", "message": ""},
    )


def _set_progress(request_id: str, current: int, total: int, stage: str, message: str = "") -> None:
    if request_id:
        _progress[request_id] = {
            "current": current,
            "total": total,
            "stage": stage,
            "message": message,
        }


def clear_progress(request_id: str) -> None:
    _progress.pop(request_id, None)
    _cancelled.discard(request_id)


def cancel_classification(request_id: str) -> None:
    """Mark a classification request as cancelled."""
    _cancelled.add(request_id)
    logger.info("Classification cancel requested: %s", request_id)


def is_cancelled(request_id: str) -> bool:
    """Check if a classification request has been cancelled."""
    return request_id in _cancelled


def _check_cancelled(request_id: str) -> None:
    """Raise CancelledError if this request has been cancelled."""
    if request_id and request_id in _cancelled:
        raise asyncio.CancelledError(f"Classification {request_id} was cancelled")


# ─── Filename tokeniser (Layer-1 helper) ───────────────────────────────────────

def _tokenize_filename(name: str) -> set[str]:
    """
    Split a filename (or keyword) into a set of meaningful lowercase tokens.

    Rules
    -----
    • Remove extension first.
    • Split on common separators: _, -, space, dot, brackets.
    • Within each segment, further split where CJK meets Latin/digit.
    • Collect 4-digit year strings as independent tokens.
    • Discard single-character tokens (too noisy).
    """
    stem = Path(name).stem.lower()
    parts = re.split(r'[_\-\s\.\(\)\[\]【】（）]+', stem)
    tokens: set[str] = set()
    for part in parts:
        if not part:
            continue
        # Split: CJK runs | Latin runs | digit runs (≥2 chars)
        for seg in re.findall(r'[\u4e00-\u9fff]+|[a-z]{2,}|\d{4}', part):
            tokens.add(seg)
    # Also pull 4-digit years from the full stem
    for yr in re.findall(r'\d{4}', stem):
        tokens.add(yr)
    return tokens


# ─── Non-sampled file assignment helper ────────────────────────────────────────

def _match_to_best_subgroup(
    files: list["ScanResult"],
    unassigned_indices: list[int],       # 1-based
    subgroups: dict[str, list[int]],     # {sub_name: [1-based idx, ...]}
    all_embeddings: "np.ndarray | None" = None,
    embedding_idx_reverse: dict[int, int] | None = None,
) -> dict[int, str]:
    """
    For files that were not in the AI sample, assign each to the most
    similar sub-group using three signals:
      1. Filename token overlap
      2. Directory co-location bonus
      3. Embedding cosine similarity (if available)

    Returns {1-based-idx: best_sub_name}.
    """
    if not unassigned_indices or not subgroups:
        fallback = next(iter(subgroups.keys()), "")
        return {idx: fallback for idx in unassigned_indices}

    import numpy as _np

    # Pre-compute token sets for each sub-group (union of member filenames)
    sub_tokens: dict[str, set[str]] = {}
    sub_dirsets: dict[str, set[str]] = {}
    for sub_name, member_indices in subgroups.items():
        tokens: set[str] = set()
        dirs: set[str] = set()
        # Also tokenize the sub-group name itself — it's a strong signal
        tokens |= _tokenize_filename(sub_name)
        for idx in member_indices:
            f = files[idx - 1]
            tokens |= _tokenize_filename(Path(f.path).name)
            dirs.add(str(Path(f.path).parent))
        sub_tokens[sub_name] = tokens
        sub_dirsets[sub_name] = dirs

    # Pre-compute embedding centroids per sub-group (if embeddings available)
    sub_centroids: dict[str, "np.ndarray"] = {}
    if all_embeddings is not None and embedding_idx_reverse is not None:
        for sub_name, member_indices in subgroups.items():
            emb_rows = [embedding_idx_reverse[idx - 1] for idx in member_indices
                        if (idx - 1) in embedding_idx_reverse]
            if emb_rows:
                centroid = _np.mean(all_embeddings[emb_rows], axis=0)
                norm = _np.linalg.norm(centroid)
                if norm > 0:
                    centroid = centroid / norm
                sub_centroids[sub_name] = centroid

    results: dict[int, str] = {}
    for idx in unassigned_indices:
        f = files[idx - 1]
        f_tokens = _tokenize_filename(Path(f.path).name)
        f_dir = str(Path(f.path).parent)

        best_name = ""
        best_score = -1.0

        # Get file embedding (if available)
        f_emb = None
        if all_embeddings is not None and embedding_idx_reverse is not None:
            idx_0 = idx - 1
            if idx_0 in embedding_idx_reverse:
                f_emb = all_embeddings[embedding_idx_reverse[idx_0]]

        for sub_name, s_tokens in sub_tokens.items():
            # Signal 1: Token overlap score
            overlap = float(len(f_tokens & s_tokens))
            # Signal 2: Directory co-location bonus
            dir_bonus = 2.0 if f_dir in sub_dirsets[sub_name] else 0.0
            # Signal 3: Embedding cosine similarity (weighted ×3.0)
            emb_score = 0.0
            if f_emb is not None and sub_name in sub_centroids:
                emb_score = float(_np.dot(f_emb, sub_centroids[sub_name])) * 3.0

            score = overlap + dir_bonus + emb_score

            if score > best_score:
                best_score = score
                best_name = sub_name

        results[idx] = best_name or next(iter(subgroups.keys()))

    return results


# ─── System prompts ────────────────────────────────────────────────────────────

SYSTEM_PROMPT_STAGE1 = """你是文件整理专家。分析以下全部文件，根据**目录结构和文件名**，识别它们的**主题/业务/项目**分组。

【最高优先级原则——目录结构决定分组】
- **同一目录下的文件几乎一定属于同一个项目**，这是最强信号
- 目录名通常直接就是项目名（如"2026美赛""法医""ESG"）
- 先观察目录结构，再根据目录名确定分组，最后提取关键词
- 每个文件后面括号中的"目录:"信息是最重要的分组依据

【绝对禁止——按文件格式/类型分组】
以下分组方式**绝对禁止**，违反此规则的输出会被直接丢弃并重新生成：
❌ "编程脚本""代码文件""MATLAB脚本""Python文件" — 按编程语言分组
❌ "文档资料""PDF文件""Word文档""学术文档" — 按文档格式分组
❌ "图片素材""图片文件""学术图表" — 按图片格式分组
❌ "压缩归档""压缩文件" — 按压缩格式分组
❌ "视频音频" — 按媒体格式分组
❌ "学习资料""其他""杂项" — 过于笼统

⚠️ 一个正确的项目分组内**应该混合包含不同类型的文件**（.py + .pdf + .xlsx + .m + .png 等），
因为同一个项目天然包含代码、文档、数据、图片。如果你的某个分组内只有单一文件类型，说明你分错了！

【正确分组维度——宜粗不宜细】
✅ 按项目/竞赛：如"2026美赛""2025国赛""亚太杯建模"
✅ 按课题/业务：如"法医DNA分析""ESG案例竞赛"
✅ 按资料集/教程：如"数学建模教程"（整个教程算一个分组，内部章节由第二阶段细分）

⚠️ 分组粒度原则：**以顶层目录为基本分组单位**。
- 同一顶层目录下的所有子目录和文件应归为**同一个分组**
- 例如"大师兄数学建模/第1讲""大师兄数学建模/第2讲"都属于"数学建模教程"这一个分组
- 不要把同一教程/资料集的不同章节拆成独立分组
- 理想的分组数量通常为 **5-15 个**，不应超过 20 个

【示例 — 注意同一分组内混合多种文件类型】
文件列表：
  1. solution.py [PY] (目录: 2026美赛/美赛)
  2. paper_final.pdf [PDF] (目录: 2026美赛/美赛)
  3. data.xlsx [XLSX] (目录: 2026美赛/美赛)
  4. analysis.m [M] (目录: 法医/Modeling)
  5. report.pdf [PDF] (目录: 法医/Modeling)
  6. 第1讲.pdf [PDF] (目录: 大师兄数学建模/第1讲 教材)
  7. example.py [PY] (目录: 大师兄数学建模/第1讲 教材)
  8. 旅行商.py [PY] (目录: 大师兄数学建模/第10讲 图论/代码)
→ {
    "2026美赛": ["美赛", "MCM", "mcm", "2026", "paper", "solution"],
    "法医DNA建模": ["法医", "forensic", "DNA", "Modeling", "analysis"],
    "数学建模教程": ["大师兄", "数学建模", "教材", "讲", "图论", "旅行商"]
  }
注意：第1讲和第10讲在同一顶层目录"大师兄数学建模"下，必须归为同一个"数学建模教程"分组！

【关键词提取规则】
- 优先从**目录名**中提取关键词（它们是最强信号）
- 其次从文件名中提取特征词
- 关键词中**不能包含文件扩展名**（如 py, pdf, xlsx, m, jpg 等都不是有效关键词）
- 同一词的中英文/大小写变体都要列出

要求：
- 分组名称语义明确（2-12 字），代表一个具体主题/业务/项目
- 分组数量由你根据实际目录结构决定，充分覆盖所有可识别的主题
- 为每个分组提供 **10-20 个关键词**，优先从目录名中提取
- 关键词必须包含该分组文件的目录名中的关键词

只返回 JSON：
{
  "projects": {
    "分组A名称": ["关键词1", "关键词2", ..., "关键词N"],
    "分组B名称": ["关键词1", "关键词2", ..., "关键词N"]
  }
}"""

SYSTEM_PROMPT_STAGE2 = """你是文件整理专家。以下文件属于同一分组，请将它们进一步细分为 2-8 个子类。

【分类策略】
- 根据文件的内容特征选择最合适的细分维度
- 可按时间段、子主题、阶段、来源、客户等维度细分——由你根据文件特点决定
- 同一目录下的文件往往有关联，可作为分组参考

【多领域示例】
分组「亚太杯数学建模」→ 子类：「2024年A题」「2024年B题」「2023年真题」「竞赛模板」
分组「法医DNA建模」→ 子类：「实验数据」「建模分析」「结果报告」「参考文献」
分组「2024年度税务」→ 子类：「增值税申报」「企业所得税」「发票与凭证」
分组「星巴克品牌VI」→ 子类：「Logo设计」「物料应用」「品牌规范」

【避免】
❌ 按文件格式细分（如"PDF文档""Excel表格""代码文件"）
❌ 泛化命名（"其他""综合""杂项"）
❌ 只有1-2个文件的子类（太细碎）

要求：
- 子类名称 2-12 字，语义明确具体
- 每个子类至少包含 2 个文件

只返回 JSON（数字为文件编号，每个文件只属于一个子类）：
{
  "subgroups": {
    "子类名称A": [1, 3],
    "子类名称B": [2, 4]
  }
}"""


SYSTEM_PROMPT_UNCERTAIN = """你是文件整理专家。以下文件无法通过关键词自动匹配到已识别的分组，请根据提供的信息将每个文件分配到最合适的分组。

【分类优先级——从高到低】
1. **所在目录路径**：同一目录下的文件大概率属于同一分组，目录名往往直接揭示主题
2. **文档标题**（如有）：比文件名更准确地反映内容主题
3. **内容摘要**：用于确认和辅助判断
4. **文件名**：最后考虑，尤其当文件名模糊时（如 1.pdf、data.xlsx）不应仅凭文件名判断

【规则】
- 优先从"可用分组"列表中选择
- 如果某些文件明显不属于任何可用分组，但彼此之间有关联，可以为它们创建一个新分组名称（2-12字，语义明确）
- 只有真正无法归类的文件才标记为"其他文件"
- 每个文件名必须出现在 assignments 中

只返回 JSON：
{
  "assignments": {
    "文件名1.pdf": "分组名称A",
    "文件名2.png": "新分组名称",
    "文件名3.txt": "其他文件"
  }
}"""


SYSTEM_PROMPT_REDISCOVER = """你是文件整理专家。第一轮分析时以下文件未被分配到任何分组。请重新审视这些文件名，识别其中可能被遗漏的主题或业务分组。

已识别的分组（不要重复）：{existing_projects}

要求：
- 只关注上述已识别分组**未覆盖**的文件，发现新的主题/业务分组
- 如果这些文件确实分散无关联，可以返回空 projects
- 每个新分组提供 10-20 个关键词，从文件名中直接提取特征词
- 绝不按文件类型分组

只返回 JSON：
{
  "projects": {
    "新分组名称": ["关键词1", "关键词2", ..., "关键词N"]
  }
}"""


REDISCOVER_THRESHOLD = 0.30  # trigger re-discovery when uncertain ratio exceeds this


SYSTEM_PROMPT_NAME_CLUSTERS = """你是文件整理专家。以下是通过内容相似度自动聚类产生的文件簇，每个簇包含几个代表性文件。
请为每个簇命名（2-12字，语义明确）。

【命名原则】
- 名称应反映簇中文件的共同主题/业务/项目
- 利用文件目录路径、文档标题、内容摘要综合判断
- 不要按文件类型命名（如"PDF文件"是错误命名）

只返回 JSON：
{
  "names": {
    "0": "簇名称A",
    "1": "簇名称B"
  }
}"""


SYSTEM_PROMPT_RECURSIVE_SPLIT = """你是文件整理专家。以下文件属于同一子文件夹，但数量过多，请将它们进一步细分为 2-8 个子类。

【分类策略】
- 根据文件的内容特征选择最合适的细分维度
- 可按时间段、子主题、阶段、来源、批次等维度细分——由你根据文件特点决定
- 同一目录下的文件往往有关联，可作为分组参考

【避免】
❌ 按文件格式细分（如"PDF文档""代码文件""表格数据"）
❌ 泛化命名（"其他""综合""杂项""工具""编译辅助"）
❌ 只有1-2个文件的子类（太细碎）

要求：
- 子类名称 2-12 字，语义明确具体
- 每个子类至少包含 2 个文件
- 每个文件只属于一个子类

只返回 JSON（数字为文件编号）：
{
  "subgroups": {
    "子类名称A": [1, 3],
    "子类名称B": [2, 4]
  }
}"""


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _safe_json(text: str) -> dict:
    """Parse JSON from AI response, stripping markdown fences if present."""
    text = text.strip()
    if not text:
        return {}
    if text.startswith("```"):
        lines = text.split("\n")
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip().startswith("```"):
            inner = inner[:-1]
        text = "\n".join(inner).strip()
    # Handle truncated JSON: try to find the outermost { ... }
    start = text.find("{")
    if start < 0:
        return {}
    # Try parsing from the first { to the end
    candidate = text[start:]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Attempt to fix truncated JSON by closing open braces/brackets
        fixed = candidate
        open_braces = fixed.count("{") - fixed.count("}")
        open_brackets = fixed.count("[") - fixed.count("]")
        if open_brackets > 0:
            fixed += "]" * open_brackets
        if open_braces > 0:
            fixed += "}" * open_braces
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI JSON (even after fix): %s…", text[:200])
            return {}


def _find_common_root(files: list[ScanResult]) -> Path:
    """Find the deepest common ancestor directory of all file paths."""
    if not files:
        return Path("/")
    parents = [Path(f.path).parent for f in files]
    common = parents[0]
    for p in parents[1:]:
        # Find common prefix parts
        while common != p and common not in p.parents:
            common = common.parent
    return common


def _build_compact_list(files: list[ScanResult], indices: list[int] | None = None) -> str:
    """
    Build a compact numbered file list (name + directory + ext + size).
    **Directory path is critical** — it's the strongest signal for project grouping.
    Shows the relative path from the common scan root so that top-level
    directories (e.g. "大师兄数学建模", "2026美赛") are always visible.
    indices: 0-based positions in `files`; if None, use all files.
    Output line numbers are 1-based (idx+1).
    """
    rows = []
    targets = indices if indices is not None else range(len(files))

    # Compute common root across all files (not just the subset) so
    # relative paths are consistent regardless of which indices are passed.
    common_root = _find_common_root(files)

    for i in targets:
        f = files[i]
        fp = Path(f.path)
        name = fp.name
        ext  = f.extension.upper().lstrip(".") or "FILE"
        mb   = f.size_bytes / 1024 / 1024
        size = f"{mb:.1f}MB" if mb >= 1 else f"{f.size_bytes // 1024}KB"
        # Relative directory from common root — keeps top-level dir visible
        try:
            rel_dir = str(fp.parent.relative_to(common_root))
        except ValueError:
            rel_dir = fp.parent.name
        if rel_dir == ".":
            rel_dir = ""
        rows.append(f"{i + 1}. {name}  [{ext}, {size}]  (目录: {rel_dir})" if rel_dir
                     else f"{i + 1}. {name}  [{ext}, {size}]")
    return "\n".join(rows)


def _sample_compact_list_by_dir(
    files: list[ScanResult], max_chars: int
) -> tuple[str, int]:
    """
    When the full file list exceeds the token budget, sample files by directory
    to ensure every directory is represented while staying within `max_chars`.

    Strategy: group files by parent directory, then take up to N files per
    directory (uniform sampling) so total output ≤ max_chars.

    Returns (compact_text, total_sampled_count).
    """
    from collections import defaultdict

    # Group file indices by parent directory
    dir_files: dict[str, list[int]] = defaultdict(list)
    for i, f in enumerate(files):
        parent = str(Path(f.path).parent)
        dir_files[parent].append(i)

    n_dirs = len(dir_files)
    if n_dirs == 0:
        return "", 0

    # Estimate chars per line (~70 chars with directory path)
    avg_line_len = 75
    max_lines = max_chars // avg_line_len

    # Calculate per-directory quota (at least 1 file per dir)
    per_dir = max(1, max_lines // n_dirs)

    sampled_indices: list[int] = []
    for parent_dir, indices in dir_files.items():
        if len(indices) <= per_dir:
            sampled_indices.extend(indices)
        else:
            # Uniform sampling: take evenly spaced files
            step = len(indices) / per_dir
            sampled_indices.extend(
                indices[int(j * step)] for j in range(per_dir)
            )

    sampled_indices.sort()
    compact = _build_compact_list(files, sampled_indices)

    # If still too long, truncate further
    if len(compact) > max_chars:
        lines = compact.split("\n")
        truncated = []
        total_len = 0
        for line in lines:
            if total_len + len(line) + 1 > max_chars:
                break
            truncated.append(line)
            total_len += len(line) + 1
        compact = "\n".join(truncated)
        sampled_indices = sampled_indices[:len(truncated)]

    logger.info("Sampled %d/%d files from %d directories for Stage-1",
                len(sampled_indices), len(files), n_dirs)
    return compact, len(sampled_indices)


def _build_content_list(
    files: list[ScanResult],
    indices: list[int],          # 1-based
    extractions: dict[int, dict],
) -> str:
    """Build a numbered file list with directory path, metadata, and content summaries."""
    rows = []
    for idx in indices:
        f      = files[idx - 1]
        name   = Path(f.path).name
        ext    = f.extension.upper().lstrip(".") or "FILE"
        # Include parent directory path for context
        parent = str(Path(f.path).parent.name) or ""
        gparent = str(Path(f.path).parent.parent.name) if len(Path(f.path).parts) > 2 else ""
        dir_ctx = f"{gparent}/{parent}" if gparent else parent

        extr    = extractions.get(idx, {})
        meta    = extr.get("metadata", {}) if isinstance(extr, dict) else {}
        title   = (meta.get("title") or "").strip()
        summary = (extr.get("summary_text") or "")[:800].replace("\n", " ")

        parts = [f"{idx}. {name}  [{ext}]  (目录: {dir_ctx})"]
        if title and title != name:
            parts.append(f"   标题：{title}")
        if summary:
            parts.append(f"   内容：{summary}")
        rows.append("\n".join(parts))
    return "\n".join(rows)


async def _call_ai(client, model: str, system: str, user: str,
                   max_tokens: int = 8192) -> str:
    """Single AI call with up to 3 retries and exponential back-off.

    Uses asyncio.wait_for as a hard timeout (180s) to prevent hangs when the
    upstream API accepts the request but takes too long to finish (e.g. reasoning
    models thinking for many minutes).
    """
    HARD_TIMEOUT = 180  # seconds — absolute upper bound per attempt

    total_chars = len(system) + len(user)
    logger.info("AI call: system=%d chars, user=%d chars, total=%d chars (≈%d tokens), max_tokens=%d",
                len(system), len(user), total_chars, total_chars // 4, max_tokens)
    for attempt in range(3):
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user",   "content": user},
                    ],
                    temperature=0.0,
                    max_tokens=max_tokens,
                    timeout=120,
                ),
                timeout=HARD_TIMEOUT,
            )
            content = response.choices[0].message.content or ""
            if not content.strip():
                if attempt < 2:
                    logger.warning("AI returned empty response (attempt %d), retrying…", attempt + 1)
                    await asyncio.sleep(2 ** attempt)
                    continue
            return content
        except asyncio.TimeoutError:
            logger.warning("AI call attempt %d hard-timeout (%ds)", attempt + 1, HARD_TIMEOUT)
            if attempt == 2:
                raise
        except Exception as e:
            if attempt == 2:
                raise
            logger.warning("AI call attempt %d failed: %s", attempt + 1, e)
        await asyncio.sleep(2 ** attempt)
    return ""


# ─── Stage-1 project-based grouping ────────────────────────────────────────────

def _parse_stage1_projects(text: str) -> dict[str, list[str]]:
    """
    Parse Stage-1 response.
    Returns {project_name: [keyword, ...]}
    """
    data     = _safe_json(text)
    projects = data.get("projects", {})
    out: dict[str, list[str]] = {}
    for name, keywords in projects.items():
        if isinstance(keywords, list):
            kws = [str(k).strip() for k in keywords if str(k).strip()]
            if kws:
                out[str(name)] = kws
    return out


# ─── Type-based group detector ────────────────────────────────────────────────

# Names that indicate grouping by file type/format — these are WRONG
_TYPE_GROUP_PATTERNS = re.compile(
    r'编程脚本|代码文件|MATLAB脚本|Python文件|脚本文件|程序代码|代码集'
    r'|文档资料|PDF文件|Word文档|学术文档|文本文件|文档集'
    r'|图片素材|图片文件|学术图表|图像文件|截图'
    r'|压缩归档|压缩文件|归档文件'
    r'|视频音频|音频文件|视频文件'
    r'|学习资料|数据文件|表格文件|Excel文件',
    re.IGNORECASE,
)


def _is_type_based_grouping(projects: dict[str, list[str]]) -> bool:
    """
    Detect if AI returned a type/format-based grouping instead of
    project/topic-based grouping. Returns True if the result looks wrong.

    Heuristic: if >40% of group names match type-based patterns, reject.
    """
    if not projects:
        return False
    type_count = sum(1 for name in projects if _TYPE_GROUP_PATTERNS.search(name))
    ratio = type_count / len(projects)
    if ratio > 0.4:
        logger.warning("Type-based grouping detected! %d/%d groups match type patterns: %s",
                        type_count, len(projects), [n for n in projects if _TYPE_GROUP_PATTERNS.search(n)])
        return True
    return False


def _filter_extension_keywords(projects: dict[str, list[str]]) -> dict[str, list[str]]:
    """
    Remove file extension keywords (py, pdf, xlsx, m, etc.) from keyword lists.
    These cause false matches across projects based on file type rather than topic.

    Smart filtering: a keyword is only removed if it exactly matches an extension
    AND is NOT a substring of the project name (e.g. "py" in "PyTorch" is kept).
    """
    ext_set = {
        'py', 'pdf', 'xls', 'xlsx', 'csv', 'doc', 'docx', 'ppt', 'pptx',
        'txt', 'md', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp',
        'tif', 'tiff', 'heic', 'mp4', 'avi', 'mov', 'zip', 'rar', '7z',
        'tar', 'gz', 'json', 'xml', 'html', 'htm', 'css',
        'js', 'ts', 'tsx', 'jsx', 'java', 'cpp', 'go', 'rs', 'rb', 'php',
        'sh', 'bat', 'exe', 'dll', 'so', 'm', 'mat',
        'ipynb', 'log', 'ini', 'cfg', 'yaml', 'yml', 'toml', 'sql', 'db',
        'sqlite', 'r', 'rmd', 'sas', 'spss',
        'psd', 'ai', 'indd', 'fig', 'svg', 'eps', 'caj', 'tex', 'bib',
        'cls', 'sty',
    }
    filtered: dict[str, list[str]] = {}
    for name, keywords in projects.items():
        name_lower = name.lower()
        clean = []
        for kw in keywords:
            kw_stripped = kw.strip().lower()
            if kw_stripped in ext_set:
                # Keep if the extension word is part of the project name
                # e.g. "py" in "PyTorch", "ai" in "AI建模"
                if kw_stripped in name_lower:
                    clean.append(kw)
                # else: filter it out
            else:
                clean.append(kw)
        if clean:
            filtered[name] = clean
        else:
            # Keep at least the original keywords if all got filtered
            filtered[name] = keywords
    return filtered


# Generic directory names that should NOT trigger strong matches.
# These are common parent folder names that carry no project-specific signal.
_GENERIC_DIR_NAMES = {
    'desktop', 'documents', 'downloads', 'projects', 'work', 'files',
    'data', 'src', 'code', 'temp', 'tmp', 'backup', 'archive', 'output',
    'out', 'build', 'dist', 'lib', 'bin', 'home', 'user', 'users',
    '桌面', '文档', '下载', '项目', '工作', '文件', '数据', '代码',
    '临时', '备份', '归档', '输出',
}


def _score_text_against_keywords(
    text: str,
    text_tokens: set[str],
    keywords: list[str],
    is_directory: bool = False,
) -> float:
    """
    Score how well `text` matches a list of keywords.

    Matching rules (per keyword):
      - Full substring match in text   → +2.0
      - Token-level overlap            → +1.0

    When `is_directory=True`, generic directory names (desktop, projects, etc.)
    are excluded from scoring to prevent false matches across projects.

    The raw sum is **normalised** by sqrt(keyword count) — a softer
    normalisation that rewards projects with more matching keywords
    while still preventing excessive keyword lists from dominating.
    """
    from math import sqrt

    # Skip scoring if directory text is a generic name
    if is_directory and text.lower() in _GENERIC_DIR_NAMES:
        return 0.0

    raw = 0.0
    for kw in keywords:
        kw_lower = kw.lower()
        # Skip generic keywords when matching directory names
        if is_directory and kw_lower in _GENERIC_DIR_NAMES:
            continue
        if kw_lower in text:
            raw += 2.0
        else:
            kw_tokens = _tokenize_filename(kw_lower) or {kw_lower}
            if kw_tokens & text_tokens:
                raw += 1.0
    return raw / sqrt(len(keywords)) if keywords else 0.0


def _assign_by_keywords(
    files: list[ScanResult],
    project_keywords: dict[str, list[str]],
) -> tuple[dict[str, list[int]], list[int]]:
    """
    Assign every file to a project group by matching project keywords
    against the filename **and directory path**.  Uses 1-based file indices.

    Scoring (per project):
      1. Filename scoring   — normalised by keyword count   (×1.0)
      2. Parent directory   — normalised by keyword count   (×3.0)
      3. Grandparent dir    — normalised by keyword count   (×2.0)

    Final score = filename_score + parent_score + grandparent_score.

    Files with score == 0 go to a dedicated "待分类" group (NOT the first
    project), preventing fallback pollution.

    Returns
    -------
    (groups, uncertain_indices)
      groups:            {project_name: [1-based-idx, ...]}
      uncertain_indices: 1-based indices of files with score == 0
    """
    groups: dict[str, list[int]] = {p: [] for p in project_keywords}
    uncertain: list[int] = []

    # Pre-compute the common root for relative path extraction
    common_root = _find_common_root(files)

    for i, f in enumerate(files, 1):
        p             = Path(f.path)
        filename      = p.name.lower()
        parent_name   = p.parent.name.lower()  if p.parent != p  else ""
        gparent_name  = p.parent.parent.name.lower() if p.parent.parent != p.parent else ""

        # Full relative directory path — captures ALL ancestor directories
        try:
            rel_dir = str(p.parent.relative_to(common_root)).lower()
        except ValueError:
            rel_dir = parent_name
        rel_dir_tokens = _tokenize_filename(rel_dir) if rel_dir and rel_dir != "." else set()

        filename_tokens = _tokenize_filename(filename)
        parent_tokens   = _tokenize_filename(parent_name)  if parent_name  else set()
        gparent_tokens  = _tokenize_filename(gparent_name) if gparent_name else set()

        best_proj  = None
        best_score = 0.0

        for proj_name, keywords in project_keywords.items():
            # Directory paths are the strongest signal — weight them heavily
            score  = _score_text_against_keywords(filename,     filename_tokens, keywords) * 1.0
            score += _score_text_against_keywords(parent_name,  parent_tokens,   keywords, is_directory=True) * 3.0
            score += _score_text_against_keywords(gparent_name, gparent_tokens,  keywords, is_directory=True) * 2.0
            # Full relative path bonus — ensures top-level dir keywords contribute
            # even for deeply nested files (e.g. 2025国赛/.../深层子目录/file.pdf)
            score += _score_text_against_keywords(rel_dir, rel_dir_tokens, keywords, is_directory=True) * 2.0

            if score > best_score:
                best_score = score
                best_proj  = proj_name

        if best_proj and best_score > 0:
            groups.setdefault(best_proj, []).append(i)
        else:
            # ── No match → dedicated "待分类" group (NOT the first project) ──
            groups.setdefault("待分类", []).append(i)
            uncertain.append(i)

    return {k: v for k, v in groups.items() if v}, uncertain


def _merge_groups_by_top_dir(
    files: list[ScanResult],
    groups: dict[str, list[int]],
    merge_threshold: float = 0.85,
) -> dict[str, list[int]]:
    """
    Merge small L1 groups that are dominated by the same top-level directory
    into the largest group for that directory.

    Only merges when ≥ merge_threshold of a group's files share the same
    top-level dir.  Skips groups larger than max_size to avoid creating
    a single catch-all group.

    This prevents the AI from creating micro-groups like "2025 国赛B题",
    "2025 国赛算法", "2025 国赛AI" — they all belong to "2025 国赛".
    """
    from collections import Counter

    common_root = _find_common_root(files)
    total_files = sum(len(v) for v in groups.values())
    # Don't merge if a group is already >40% of all files (it's a catch-all)
    max_group_size = int(total_files * 0.4)

    # Determine dominant top-level dir for each group
    group_top_dir: dict[str, str | None] = {}
    for gname, idxs in groups.items():
        if gname == "待分类" or len(idxs) > max_group_size:
            group_top_dir[gname] = None
            continue
        top_counts: Counter[str] = Counter()
        for idx in idxs:
            p = Path(files[idx - 1].path)
            try:
                rel = p.relative_to(common_root)
                top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            except ValueError:
                top = "(root)"
            top_counts[top] += 1
        dominant_dir, dominant_count = top_counts.most_common(1)[0]
        ratio = dominant_count / len(idxs)
        group_top_dir[gname] = dominant_dir if ratio >= merge_threshold else None

    # Group names by their dominant top-level dir
    dir_to_groups: dict[str, list[str]] = {}
    for gname, top_dir in group_top_dir.items():
        if top_dir is not None:
            dir_to_groups.setdefault(top_dir, []).append(gname)

    # Merge: for each top-level dir with multiple groups, keep the largest
    merged = dict(groups)
    for top_dir, gnames in dir_to_groups.items():
        if len(gnames) <= 1:
            continue
        # Sort by size descending — keep largest name
        gnames.sort(key=lambda g: len(merged.get(g, [])), reverse=True)
        primary = gnames[0]
        did_merge = False
        for secondary in gnames[1:]:
            if secondary in merged:
                # Don't merge if it would make the primary too large
                if len(merged[primary]) + len(merged[secondary]) > max_group_size:
                    continue
                logger.info("Merging group '%s' (%d files) into '%s' (%d files) — same top dir '%s'",
                            secondary, len(merged[secondary]), primary, len(merged[primary]), top_dir)
                merged[primary].extend(merged.pop(secondary))
                did_merge = True

        # After merging, rename to the top-level directory name if we merged anything
        if did_merge and primary != top_dir:
            merged[top_dir] = merged.pop(primary)
            logger.info("Renamed merged group '%s' → '%s'", primary, top_dir)

    return merged


def _absorb_tiny_groups(
    files: list[ScanResult],
    groups: dict[str, list[int]],
    min_size: int = 10,
) -> dict[str, list[int]]:
    """
    Absorb tiny groups (< min_size files) into the best-matching large group.

    Matching is based on the dominant top-level directory of the tiny group's
    files.  If no directory match is found, absorb into the largest group.
    """
    from collections import Counter

    common_root = _find_common_root(files)

    tiny = {g: idxs for g, idxs in groups.items() if len(idxs) < min_size and g != "待分类"}
    large = {g: idxs for g, idxs in groups.items() if len(idxs) >= min_size or g == "待分类"}

    if not tiny:
        return groups

    # For each large group, compute its dominant top-level dir
    large_top_dirs: dict[str, Counter] = {}
    for gname, idxs in large.items():
        if gname == "待分类":
            continue
        tc: Counter[str] = Counter()
        for idx in idxs:
            p = Path(files[idx - 1].path)
            try:
                rel = p.relative_to(common_root)
                tc[rel.parts[0] if len(rel.parts) > 1 else "(root)"] += 1
            except ValueError:
                pass
        large_top_dirs[gname] = tc

    result = dict(large)
    for tg, tidxs in tiny.items():
        # Find dominant top-level dir for tiny group
        tc: Counter[str] = Counter()
        for idx in tidxs:
            p = Path(files[idx - 1].path)
            try:
                rel = p.relative_to(common_root)
                tc[rel.parts[0] if len(rel.parts) > 1 else "(root)"] += 1
            except ValueError:
                pass

        tiny_top = tc.most_common(1)[0][0] if tc else "(root)"

        # Find the large group with most files from the same top dir
        best_match = None
        best_count = 0
        for lg, lg_tc in large_top_dirs.items():
            count = lg_tc.get(tiny_top, 0)
            if count > best_count:
                best_count = count
                best_match = lg

        if not best_match:
            # Fallback: largest group
            best_match = max(result.keys(), key=lambda g: len(result[g]) if g != "待分类" else 0)

        logger.info("Absorbing tiny group '%s' (%d files) into '%s' — top dir '%s'",
                    tg, len(tidxs), best_match, tiny_top)
        result[best_match].extend(tidxs)

    return result


def _time_cluster_rescue(
    files: list[ScanResult],
    groups: dict[str, list[int]],
    uncertain: list[int],
    window_days: int = TIME_CLUSTER_DAYS,
) -> tuple[dict[str, list[int]], list[int]]:
    """
    Rescue uncertain files via time-clustering: if a file's mtime falls
    within `window_days` of confirmed files in a project, assign it there.

    Modifies `groups` in place and returns (groups, remaining_uncertain).
    """
    if not uncertain:
        return groups, uncertain

    from datetime import datetime, timezone

    # Build {project → [mtime_epoch, ...]} from confirmed files
    project_times: dict[str, list[float]] = {}
    confirmed = {idx for proj, idxs in groups.items() if proj != "待分类" for idx in idxs}
    for proj, idxs in groups.items():
        if proj == "待分类":
            continue
        times = []
        for idx in idxs:
            mt = files[idx - 1].modified_time
            try:
                t = datetime.fromisoformat(mt).timestamp()
                times.append(t)
            except Exception:
                pass
        if times:
            project_times[proj] = times

    if not project_times:
        return groups, uncertain

    window = window_days * 86400
    still_uncertain: list[int] = []

    for idx in uncertain:
        mt = files[idx - 1].modified_time
        try:
            file_ts = datetime.fromisoformat(mt).timestamp()
        except Exception:
            still_uncertain.append(idx)
            continue

        best_proj = None
        best_dist = float("inf")
        for proj, timestamps in project_times.items():
            min_dist = min(abs(file_ts - t) for t in timestamps)
            if min_dist <= window and min_dist < best_dist:
                best_dist = min_dist
                best_proj = proj

        if best_proj:
            groups.setdefault(best_proj, []).append(idx)
            # Remove from "待分类" group
            if "待分类" in groups and idx in groups["待分类"]:
                groups["待分类"].remove(idx)
        else:
            still_uncertain.append(idx)

    # Clean up empty "待分类"
    if "待分类" in groups and not groups["待分类"]:
        del groups["待分类"]

    return groups, still_uncertain


def _directory_based_fallback(files: list[ScanResult]) -> dict[str, list[str]]:
    """
    When AI returns type-based grouping (e.g. "编程脚本", "文档资料"),
    fall back to directory-structure-based grouping.

    Uses the top-level directory relative to the common scan root as the
    project name, and extracts keywords from directory names.
    """
    from collections import Counter

    # Find common prefix of all file paths
    all_parents = [str(Path(f.path).parent) for f in files]
    if not all_parents:
        return {}

    # Find common root
    common = Path(all_parents[0])
    for p in all_parents[1:]:
        while not p.startswith(str(common)):
            common = common.parent
            if common == common.parent:
                break

    common_str = str(common).rstrip("/") + "/"

    # Group by first-level directory under common root
    dir_groups: dict[str, int] = Counter()
    for f in files:
        rel = str(Path(f.path).parent)
        if rel.startswith(common_str):
            rel_from_root = rel[len(common_str):]
            top_dir = rel_from_root.split("/")[0] if rel_from_root else ""
        else:
            top_dir = ""
        if top_dir:
            dir_groups[top_dir] += 1
        else:
            dir_groups["根目录文件"] += 1

    # Build project keywords from directory names
    projects: dict[str, list[str]] = {}
    for dir_name, count in dir_groups.items():
        if count < 1:
            continue
        # Tokenize directory name for keywords
        tokens = _tokenize_filename(dir_name)
        keywords = list(tokens) + [dir_name]
        # Also add the full directory name as-is (case-insensitive matching)
        if dir_name.lower() not in {k.lower() for k in keywords}:
            keywords.append(dir_name.lower())
        projects[dir_name] = keywords

    logger.info("Directory-based fallback: %d groups from directory structure: %s",
                len(projects), list(projects.keys()))
    return projects


def _token_fallback_groups(
    files: list[ScanResult],
    max_groups: int = 5,
) -> dict[str, list[int]]:
    """
    Token-based project grouping when Stage-1 AI fails.

    Strategy
    --------
    1. Tokenise every filename: CJK words (2-4 chars), uppercase abbreviations,
       4-digit years.
    2. Find tokens that appear in 2%-25% of files — these are likely project
       identifiers (not too common, not too rare).
    3. For each file, pick the *rarest* matching candidate token as its
       project label.
    4. Merge tiny groups into "其他文件".
    """
    n = len(files)

    def _tokenize(name: str) -> list[str]:
        return re.findall(
            r"[\u4e00-\u9fff]{2,4}|[A-Z]{2,}(?:[A-Za-z]*)?|\d{4}",
            name,
        )

    all_tokens: Counter = Counter()
    file_token_sets: list[set[str]] = []

    for f in files:
        tokens = set(_tokenize(Path(f.path).name))
        file_token_sets.append(tokens)
        all_tokens.update(tokens)

    # Noise tokens that should never become group names
    _NOISE_TOKENS = {
        "副本", "未命名", "新建", "新建文件夹", "拷贝", "备份", "临时",
        "untitled", "copy", "temp", "tmp", "new", "backup", "desktop",
    }

    min_c = max(2, int(n * 0.02))
    max_c = max(min_c + 1, int(n * 0.25))
    candidates = {
        t: c for t, c in all_tokens.items()
        if min_c <= c <= max_c and t.lower() not in _NOISE_TOKENS
    }

    if not candidates:
        return {"文件集合": list(range(1, n + 1))}

    groups: dict[str, list[int]] = {}
    for i, tokens in enumerate(file_token_sets, 1):
        matching = [(t, candidates[t]) for t in tokens if t in candidates]
        if matching:
            best = min(matching, key=lambda x: x[1])[0]   # rarest = most distinctive
            groups.setdefault(best, []).append(i)
        else:
            groups.setdefault("其他文件", []).append(i)

    # Merge tiny groups and keep top max_groups
    min_size   = max(2, int(n * 0.01))
    large      = {k: v for k, v in groups.items() if len(v) >= min_size and k != "其他文件"}
    top_groups = dict(sorted(large.items(), key=lambda x: -len(x[1]))[:max_groups])

    kept = {i for v in top_groups.values() for i in v}
    leftover = [i for i in range(1, n + 1) if i not in kept]
    if leftover:
        top_groups["其他文件"] = leftover

    return top_groups


# ─── Single-pass helpers ────────────────────────────────────────────────────────

def _parse_single(text: str, n: int) -> dict[int, tuple[str, str]]:
    """Parse single-pass response → {1-based-idx: (level1, level2)}."""
    data      = _safe_json(text)
    hierarchy = data.get("hierarchy", {})
    out: dict[int, tuple[str, str]] = {}
    for l1, subs in hierarchy.items():
        if not isinstance(subs, dict):
            continue
        for l2, idxs in subs.items():
            if not isinstance(idxs, list):
                continue
            for idx in idxs:
                if isinstance(idx, int) and 1 <= idx <= n:
                    out[idx] = (str(l1), str(l2))
    return out


def _parse_subgroups(text: str, valid: set[int]) -> dict[str, list[int]]:
    """Parse stage-2 response → {subgroup_name: [1-based-idx, ...]}."""
    data = _safe_json(text)
    subs = data.get("subgroups", {})
    out: dict[str, list[int]] = {}
    for name, idxs in subs.items():
        if not isinstance(idxs, list):
            continue
        good = [i for i in idxs if isinstance(i, int) and i in valid]
        if good:
            out[str(name)] = good
    return out


# ─── Layer-2: content-based fallback for uncertain text files ──────────────────

def _content_char_limit(ext: str) -> int:
    """
    Return the character limit for Layer-2 content extraction based on file type.

    Design rationale
    ----------------
    With UNCERTAIN_BATCH=50 and a ~3 000 char/file budget the batch payload is
    ≈ 150 K chars ≈ 37 K tokens — comfortably within 128 K context models.

    Limits are chosen to maximise signal-to-noise:
      • Code   : first ~60 lines (imports + class/function signatures are most
                 distinctive; diminishing returns beyond that)
      • Text/MD: first 800 chars (title + opening paragraphs are definitive)
      • Docs   : first 600 chars (document title / abstract)
      • Tables : first 400 chars (column headers + a few rows suffice)
      • Default: 400 chars
    """
    ext = ext.lower()
    if ext in _CODE_EXTS:
        return 2000    # ≈ 80 lines — imports + signatures + key logic
    if ext in _TEXT_EXTS:
        return 1200    # title + several paragraphs
    if ext in _DOC_EXTS:
        return 1200    # abstract / introduction
    if ext in _TABLE_EXTS:
        return 600     # headers + several rows
    return 600


async def _classify_uncertain_by_content(
    client,
    model: str,
    uncertain_files: list[tuple[int, "ScanResult"]],  # (1-based-idx, file)
    project_names: list[str],
    request_id: str,
    progress_base: int,
    n_total: int,
) -> dict[int, str]:
    """
    For text files that scored 0 in keyword matching, extract their content
    and batch-ask AI to assign them to the best-fitting project.

    Returns {1-based-idx: project_name}
    """
    if not uncertain_files or not project_names:
        return {}

    results: dict[int, str] = {}
    batches = [
        uncertain_files[i: i + UNCERTAIN_BATCH]
        for i in range(0, len(uncertain_files), UNCERTAIN_BATCH)
    ]
    projects_str = "、".join(f"「{p}」" for p in project_names)

    for b_idx, batch in enumerate(batches):
        _set_progress(
            request_id,
            progress_base + int(b_idx / len(batches) * (n_total * 0.05)),
            n_total, "内容兜底",
            f"正在二次分析 {len(batch)} 个未匹配文件（批次 {b_idx+1}/{len(batches)}）…",
        )
        lines = []
        name_to_idx: dict[str, int] = {}
        for idx, f in batch:
            name = Path(f.path).name
            ext  = Path(f.path).suffix
            name_to_idx[name] = idx

            # Directory context — often the strongest signal for vague filenames
            parent = Path(f.path).parent.name or ""
            gparent = Path(f.path).parent.parent.name if len(Path(f.path).parts) > 2 else ""
            dir_ctx = f"{gparent}/{parent}" if gparent else parent

            try:
                extr    = await asyncio.to_thread(extract, Path(f.path))
                limit   = _content_char_limit(ext)
                summary = (extr.get("summary_text") or "")[:limit].replace("\n", " ")
                meta    = extr.get("metadata", {}) if isinstance(extr, dict) else {}
                title   = (meta.get("title") or "").strip()
            except Exception:
                summary = ""
                title   = ""

            parts = [f"- {name}  (所在目录: {dir_ctx})"]
            if title and title != name:
                parts.append(f"  标题：{title}")
            if summary:
                parts.append(f"  内容：{summary}")
            lines.append("\n".join(parts))

        user_msg = (
            f"可用项目：{projects_str}\n\n"
            f"以下 {len(batch)} 个文件无法通过关键词匹配，请逐一分配到最合适的项目：\n\n"
            + "\n".join(lines)
        )
        try:
            raw  = await _call_ai(client, model, SYSTEM_PROMPT_UNCERTAIN, user_msg)
            data = _safe_json(raw)
            asns = data.get("assignments", {})
            for name, proj in asns.items():
                if name in name_to_idx and proj:
                    # Accept both existing projects and AI-created new group names
                    results[name_to_idx[name]] = proj
        except Exception as e:
            logger.warning("Layer-2 batch %d failed: %s", b_idx, e)

        # Files not returned by AI remain unassigned (will go to "其他文件" later)

    return results


# ─── Image classification — Layer A / B / C ────────────────────────────────────

def _image_rule_classify(f: "ScanResult") -> tuple[str, str | None]:
    """
    Layer A: classify an image by EXIF date and filename pattern.

    Returns
    -------
    (category, date_str)
      category  : "截图" | "微信图片" | "手机照片" | "照片" | "图片"
      date_str  : "YYYY-MM" string or None
    """
    name = Path(f.path).name
    stem = Path(f.path).stem

    # Pattern: screenshot
    if _RE_SCREENSHOT.search(name):
        # Try to extract date from filename (e.g. "Screenshot_20250301_...")
        m = re.search(r'(\d{4})(\d{2})\d{2}', stem)
        return "截图", (f"{m.group(1)}-{m.group(2)}" if m else None)

    # Pattern: WeChat export (filename contains Unix timestamp in ms, e.g. mmexport1709274000000)
    if _RE_WECHAT.search(name):
        ts_match = re.search(r'(\d{13})', stem)   # 13-digit ms timestamp
        if ts_match:
            import datetime as _dt
            try:
                ts = int(ts_match.group(1)) // 1000
                d  = _dt.datetime.utcfromtimestamp(ts)
                return "微信图片", f"{d.year}-{d.month:02d}"
            except Exception:
                pass
        m = re.search(r'(\d{4})(0[1-9]|1[0-2])(\d{2})', stem)
        return "微信图片", (f"{m.group(1)}-{m.group(2)}" if m else None)

    # Try EXIF date (most reliable for real photos)
    try:
        from analyzer.image_extractor import extract_image as _xi
        meta = _xi(Path(f.path))
        dt   = meta.get("metadata", {}).get("date_taken", "")
        if dt and len(dt) >= 7:
            year_month = dt[:7].replace(":", "-")   # "2025:03:01…" → "2025-03"
            cat = "手机照片" if _RE_PHONE_PHOTO.match(name) else "照片"
            return cat, year_month
    except Exception:
        pass

    # Phone-style filename but no EXIF
    m = re.search(r'(\d{4})(0[1-9]|1[0-2])(\d{2})', stem)
    if _RE_PHONE_PHOTO.match(name):
        return "手机照片", (f"{m.group(1)}-{m.group(2)}" if m else None)

    return "图片", None


async def _classify_images_by_vision(
    client,
    model: str,
    image_files: list[tuple[int, "ScanResult"]],
    project_names: list[str],
) -> dict[int, str]:
    """
    Layer C: send thumbnail to a vision-capable model and ask which project
    it belongs to.  Silently falls back to the first project if the model
    doesn't support vision or if any other error occurs.
    """
    import base64, io
    fallback = project_names[0] if project_names else "其他图片"
    projects_str = "、".join(f"「{p}」" for p in project_names)
    results: dict[int, str] = {}

    for idx, f in image_files:
        try:
            from PIL import Image
            img = Image.open(str(f.path)).convert("RGB")
            img.thumbnail((512, 512))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            b64 = base64.b64encode(buf.getvalue()).decode()

            resp = await client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": (
                                f"这张图片最可能属于以下哪个项目？{projects_str}\n"
                                "只回复项目名称，不要解释。"
                            ),
                        },
                    ],
                }],
                max_tokens=30,
                timeout=30,
            )
            reply = (resp.choices[0].message.content or "").strip()
            matched = next((p for p in project_names if p in reply), None)
            results[idx] = matched or fallback
        except Exception as e:
            logger.debug("Vision AI skipped for %s: %s", Path(f.path).name, e)
            results[idx] = fallback

    return results


async def _classify_images(
    client,
    model: str,
    image_indices: list[int],
    files: list["ScanResult"],
    text_assignments: dict[int, list[str]],
    project_names: list[str],
    request_id: str,
    progress_base: int,
    n_total: int,
) -> dict[int, tuple[str, str]]:
    """
    Three-layer image classification pipeline.

    Layer B (co-location) → Layer A (EXIF/pattern) → Layer C (Vision AI)

    Returns {1-based-idx: (level1, level2)}
    """
    if not image_indices:
        return {}

    _set_progress(request_id, progress_base, n_total, "图片分析",
                  f"正在分析 {len(image_indices)} 张图片…")

    # Build directory → most common project map from text file assignments (Layer B)
    from collections import Counter as _Counter
    dir_votes: dict[str, _Counter] = {}
    for idx, segs in text_assignments.items():
        l1 = segs[0] if segs else "其他文件"
        d = str(Path(files[idx - 1].path).parent)
        dir_votes.setdefault(d, _Counter())[l1] += 1
    dir_to_project = {d: c.most_common(1)[0][0] for d, c in dir_votes.items()}

    def _find_project_by_ancestors(img_path: str) -> str | None:
        """Walk up the directory tree to find a matching project via co-location."""
        p = Path(img_path).parent
        # Check up to 4 ancestor levels
        for _ in range(4):
            d = str(p)
            if d in dir_to_project:
                return dir_to_project[d]
            # Also check if any known directory starts with this ancestor
            # (i.e. this ancestor is a parent of a known project directory)
            for known_dir, proj in dir_to_project.items():
                if known_dir.startswith(d + "/"):
                    return proj
            if p.parent == p:
                break
            p = p.parent
        return None

    results: dict[int, tuple[str, str]] = {}
    vision_needed: list[tuple[int, "ScanResult"]] = []

    for idx in image_indices:
        f       = files[idx - 1]

        # ── Layer B: co-location (check current dir + ancestor dirs) ─────────
        proj = _find_project_by_ancestors(f.path)
        if proj:
            results[idx] = (proj, "过程图片")
            continue

        # ── Layer A: EXIF + filename pattern ──────────────────────────────────
        category, date_str = _image_rule_classify(f)
        if date_str:
            # Known category with date → use date as the L2 subfolder
            results[idx] = (category, date_str)
        elif category != "图片":
            # Recognised type (screenshot / WeChat) but no date
            results[idx] = (category, category)
        else:
            # Cannot determine from metadata → Queue for Vision AI
            vision_needed.append((idx, f))

    # ── Layer C: Vision AI ────────────────────────────────────────────────────
    if vision_needed and project_names:
        _set_progress(request_id, progress_base, n_total, "图片分析",
                      f"Vision AI 分析 {len(vision_needed)} 张图片…")
        vision_results = await _classify_images_by_vision(
            client, model, vision_needed, project_names
        )
        for idx, proj in vision_results.items():
            results[idx] = (proj, "相关图片")

    # Fallback: any image still unresolved
    fallback_proj = project_names[0] if project_names else "待整理图片"
    for idx in image_indices:
        if idx not in results:
            results[idx] = (fallback_proj, "待整理图片")

    return results


# ─── Stage 3: recursive subdivision ────────────────────────────────────────────

async def _recursive_subdivide_all(
    client,
    model: str,
    files: list["ScanResult"],
    assignments_by_idx: dict[int, list[str]],
    extractions: dict[int, dict],
    request_id: str,
    n_total: int,
    all_embeddings: "np.ndarray | None" = None,
    embedding_idx_map: list[int] | None = None,
    embedding_idx_reverse: dict[int, int] | None = None,
) -> None:
    """
    After Stage 2, find leaf folders that still have too many files
    (> SPLIT_THRESHOLD) and recursively subdivide them via AI.

    Modifies `assignments_by_idx` in place — appends deeper path segments.
    """
    # Group indices by their current full path
    from collections import defaultdict

    def _path_key(segs: list[str]) -> str:
        return "\0".join(segs)

    def _gather_leaves() -> dict[str, list[int]]:
        """Return {path_key: [indices]} for all current leaf folders."""
        leaves: dict[str, list[int]] = defaultdict(list)
        for idx, segs in assignments_by_idx.items():
            leaves[_path_key(segs)].append(idx)
        return dict(leaves)

    max_rounds = MAX_DEPTH - 2   # Stage 1 + Stage 2 already gave 2 levels
    prev_large_keys: set[str] = set()  # track previous round's large leaves to detect no-progress
    for round_num in range(max_rounds):
        leaves = _gather_leaves()
        # Find leaves that are too large
        # Skip "其他文件" and "待分类" — they contain unrelated files, splitting is meaningless
        large_leaves = {k: idxs for k, idxs in leaves.items()
                        if len(idxs) > SPLIT_THRESHOLD
                        and not k.startswith("其他文件")
                        and not k.startswith("待分类")
                        and not k.startswith("其他")}
        if not large_leaves:
            break

        # Termination: if the same leaves are still large (no progress), stop
        current_large_keys = set(large_leaves.keys())
        if current_large_keys == prev_large_keys:
            logger.info("Recursive split round %d: no progress (same %d leaves still large), stopping",
                        round_num + 1, len(current_large_keys))
            break
        prev_large_keys = current_large_keys

        logger.info("Recursive split round %d: %d large leaves to subdivide",
                    round_num + 1, len(large_leaves))

        sem = asyncio.Semaphore(5)

        async def _split_leaf(path_key: str, leaf_indices: list[int]) -> None:
            async with sem:
                parent_segs = path_key.split("\0")
                depth = len(parent_segs)
                if depth >= MAX_DEPTH:
                    return

                folder_name = parent_segs[-1] if parent_segs else "文件夹"

                # Try embedding clustering first (faster & avoids slow AI calls)
                if len(leaf_indices) >= 10 and all_embeddings is not None and embedding_idx_reverse is not None:
                    leaf_emb_rows = []
                    leaf_emb_to_idx = []
                    for idx_1based in leaf_indices:
                        idx_0based = idx_1based - 1
                        if idx_0based in embedding_idx_reverse:
                            emb_row = embedding_idx_reverse[idx_0based]
                            leaf_emb_rows.append(emb_row)
                            leaf_emb_to_idx.append(idx_1based)

                    if len(leaf_emb_rows) >= 10:
                        leaf_embeddings = all_embeddings[leaf_emb_rows]
                        clusters = cluster_embeddings(leaf_embeddings, min_cluster_size=5, max_clusters=6)
                        real_clusters = {k: v for k, v in clusters.items() if k != -1}

                        if len(real_clusters) >= 2:
                            # Build naming prompt
                            cluster_descs = []
                            for cid, local_indices in sorted(real_clusters.items()):
                                reps = get_representative_indices(leaf_embeddings, local_indices, n_representatives=4)
                                rep_lines = []
                                for li in reps:
                                    idx_1b = leaf_emb_to_idx[li]
                                    f = files[idx_1b - 1]
                                    nm = Path(f.path).name
                                    pr = Path(f.path).parent.name or ""
                                    rep_lines.append(f"  - {nm}  (目录: {pr})")
                                cluster_descs.append(f"簇 {cid}（{len(local_indices)} 个文件）：\n" + "\n".join(rep_lines))

                            user_naming = (
                                f'文件夹「{folder_name}」包含 {len(leaf_indices)} 个文件，'
                                f'已自动聚类为 {len(real_clusters)} 个子簇。\n'
                                f'请为每个簇命名：\n\n' + "\n\n".join(cluster_descs)
                            )
                            # Try AI naming; fallback to auto-generated names on failure
                            names_map: dict[str, str] = {}
                            try:
                                raw = await _call_ai(client, model, SYSTEM_PROMPT_NAME_CLUSTERS, user_naming)
                                data = _safe_json(raw)
                                names_map = {str(k): str(v) for k, v in data.get("names", {}).items()}
                            except Exception as e:
                                logger.warning("Embedding naming AI failed for '%s', using auto names: %s", folder_name, e)

                            # Build auto-names from representative filenames as fallback
                            def _auto_name(cid: int, local_idxs: list[int]) -> str:
                                if str(cid) in names_map and names_map[str(cid)].strip():
                                    return names_map[str(cid)].strip()
                                # Use most common parent dir or first representative filename
                                rep = get_representative_indices(leaf_embeddings, local_idxs, n_representatives=2)
                                parts = []
                                for li in rep[:2]:
                                    idx_1b = leaf_emb_to_idx[li]
                                    stem = Path(files[idx_1b - 1].path).stem
                                    if len(stem) > 15:
                                        stem = stem[:15]
                                    parts.append(stem)
                                return "、".join(parts) if parts else f"子类{cid+1}"

                            subs: dict[str, list[int]] = {}
                            for cid, local_indices in real_clusters.items():
                                sub_name = _auto_name(cid, local_indices)
                                for li in local_indices:
                                    idx_1b = leaf_emb_to_idx[li]
                                    assignments_by_idx[idx_1b] = parent_segs + [sub_name]
                                subs[sub_name] = [leaf_emb_to_idx[li] for li in local_indices]

                            # Noise → nearest cluster
                            noise_local = clusters.get(-1, [])
                            if noise_local:
                                c_centroids = compute_centroids(
                                    leaf_embeddings,
                                    {str(cid): idxs for cid, idxs in real_clusters.items()}
                                )
                                cid_to_name = {str(cid): _auto_name(cid, real_clusters[cid]) for cid in real_clusters}
                                noise_embs = leaf_embeddings[noise_local]
                                noise_assigns = assign_to_nearest(noise_embs, c_centroids, threshold=0.0)
                                for i, (best_cid, _) in enumerate(noise_assigns):
                                    idx_1b = leaf_emb_to_idx[noise_local[i]]
                                    sub_name = cid_to_name.get(best_cid, next(iter(subs.keys())))
                                    assignments_by_idx[idx_1b] = parent_segs + [sub_name]

                            # Files without embeddings → filename match
                            no_emb = [idx for idx in leaf_indices if idx not in {leaf_emb_to_idx[li] for li in range(len(leaf_emb_to_idx))}]
                            if no_emb and subs:
                                matches = _match_to_best_subgroup(files, no_emb, subs,
                                                                   all_embeddings, embedding_idx_reverse)
                                for idx, sub_name in matches.items():
                                    assignments_by_idx[idx] = parent_segs + [sub_name]

                            logger.info("Recursive split (embedding) '%s': %d files → %d sub-clusters",
                                        folder_name, len(leaf_indices), len(subs))
                            return

                if len(leaf_indices) > 200:
                    # Fallback: filename-only compact list
                    sample = leaf_indices
                    compact_0based = [idx - 1 for idx in leaf_indices]
                    batch = min(80, len(leaf_indices))
                    step = max(1, len(compact_0based) // batch)
                    sampled_0based = compact_0based[::step][:batch]
                    file_list = _build_compact_list(files, sampled_0based)
                    user_msg = (
                        f'文件夹「{folder_name}」包含 {len(leaf_indices)} 个文件，'
                        f'数量过多，请根据文件名模式（年份、题号、章节等）进一步细分：\n\n{file_list}'
                    )
                else:
                    # Smaller group — use content summaries for better accuracy
                    if len(leaf_indices) > MAX_S2_SAMPLE:
                        step = max(1, len(leaf_indices) // MAX_S2_SAMPLE)
                        sample = leaf_indices[::step][:MAX_S2_SAMPLE]
                    else:
                        sample = leaf_indices

                    new_to_extract = [idx for idx in sample if idx not in extractions]
                    if new_to_extract:
                        tasks = [asyncio.to_thread(extract, Path(files[idx - 1].path))
                                 for idx in new_to_extract]
                        results = await asyncio.gather(*tasks, return_exceptions=True)
                        for idx, result in zip(new_to_extract, results):
                            extractions[idx] = result if not isinstance(result, Exception) else {}

                    file_list = _build_content_list(files, sample, extractions)
                    note = (f"（代表性样本 {len(sample)}/{len(leaf_indices)} 个）"
                            if len(sample) < len(leaf_indices) else "")
                    user_msg = (
                        f'文件夹「{folder_name}」{note}包含 {len(leaf_indices)} 个文件，'
                        f'数量过多，请进一步细分：\n\n{file_list}'
                    )

                try:
                    raw = await _call_ai(client, model,
                                         SYSTEM_PROMPT_RECURSIVE_SPLIT, user_msg)
                    subs = _parse_subgroups(raw, set(sample))

                    if not subs:
                        logger.warning("Recursive split for '%s' (%d files): AI returned empty, skipping",
                                       folder_name, len(leaf_indices))
                        return
                    if len(subs) <= 1:
                        logger.info("Recursive split for '%s': AI returned 1 group, no further split",
                                    folder_name)
                        return

                    assigned_here: set[int] = set()
                    for sub_name, s_indices in subs.items():
                        for idx in s_indices:
                            assignments_by_idx[idx] = parent_segs + [sub_name]
                            assigned_here.add(idx)

                    # Non-sampled files → match to closest sub-group
                    unassigned = [idx for idx in leaf_indices if idx not in assigned_here]
                    if unassigned and subs:
                        matches = _match_to_best_subgroup(files, unassigned, subs,
                                                           all_embeddings, embedding_idx_reverse)
                        for idx, sub_name in matches.items():
                            assignments_by_idx[idx] = parent_segs + [sub_name]

                    logger.info("Split '%s' (%d files) into %d sub-groups: %s",
                                folder_name, len(leaf_indices), len(subs), list(subs.keys()))
                except Exception as e:
                    logger.warning("Recursive split failed for '%s': %s", folder_name, e)

        await asyncio.gather(*[_split_leaf(k, idxs) for k, idxs in large_leaves.items()])


# ─── Main entry point ──────────────────────────────────────────────────────────

async def classify_tree(
    files: list[ScanResult],
    ai_config: AiConfig,
    request_id: str = "",
) -> dict:
    """
    Classify files into a dynamic AI-generated multi-level folder hierarchy,
    grouped by **project / topic** rather than file type.

    Returns
    -------
    {
        "tree": {name: {"files": [...], "children": {name: node, ...}}, ...},
        "assignments": {"/abs/path/file.pdf": {"sub_path": ["L1", "L2", "L3"]}}
    }
    """
    from openai import AsyncOpenAI
    import httpx as _httpx

    client = AsyncOpenAI(
        api_key=ai_config.api_key,
        base_url=ai_config.base_url,
        timeout=_httpx.Timeout(180, connect=30),
    )

    import numpy as np

    n = len(files)
    assignments_by_idx: dict[int, list[str]] = {}   # idx → [L1, L2, L3, ...]
    uncertain_1based: list[int] = []   # files with no keyword match (score == 0)

    _set_progress(request_id, 0, n, "准备中", "正在初始化分析…")
    _check_cancelled(request_id)

    # ── Pre-filter: separate dev-artifact files from real content files ────────
    # Dev artifacts (venv, node_modules, __pycache__, .idea, etc.) are excluded
    # from AI classification to avoid noise, but kept in final results — they
    # are auto-assigned to their parent project group after classification.
    _DEV_ARTIFACT_DIRS = {
        "venv", ".venv", "env", ".env", "__pycache__", ".mypy_cache", ".pytest_cache",
        "site-packages", "dist-packages", ".eggs",
        "node_modules", ".next", ".nuxt",
        ".cache", ".parcel-cache",
        ".idea", ".vscode",
    }

    def _is_dev_artifact(path: Path, common: Path) -> bool:
        try:
            rel = path.relative_to(common)
        except ValueError:
            return False
        for part in rel.parts:
            if part in _DEV_ARTIFACT_DIRS or part.endswith(".egg-info"):
                return True
        return False

    common_root_pre = _find_common_root(files)
    dev_artifact_indices: set[int] = set()  # 0-based indices of dev artifact files
    real_files: list[ScanResult] = []       # files sent to AI classification
    real_to_original: list[int] = []        # maps real_files index → original files index (0-based)

    for i, f in enumerate(files):
        if _is_dev_artifact(Path(f.path), common_root_pre):
            dev_artifact_indices.add(i)
        else:
            real_to_original.append(i)
            real_files.append(f)

    logger.info("Pre-filter: %d total files, %d dev artifacts excluded from classification, %d real files",
                n, len(dev_artifact_indices), len(real_files))

    # Use real_files for all classification stages; dev artifacts will be
    # back-filled into their parent project group at the end.
    # Replace 'files' with 'real_files' for all classification logic below.
    original_files = files
    n_total = n  # keep original total for progress display
    files = real_files
    n = len(files)  # n now refers to real files count for all downstream logic

    # ── Stage 0: extract content & generate embeddings ───────────────────────────
    _set_progress(request_id, 0, n, "内容提取", "正在提取文件内容并生成语义向量…")

    # Identify non-image files for embedding
    non_image_indices = [
        i for i in range(n)
        if Path(files[i].path).suffix.lower() not in _IMAGE_EXTS
    ]

    # Parallel content extraction for all non-image files
    extractions_all: dict[int, dict] = {}  # 1-based idx → extraction result
    extract_tasks = [
        asyncio.to_thread(extract, Path(files[i].path))
        for i in non_image_indices
    ]
    if extract_tasks:
        logger.info("Stage-0: extracting content from %d non-image files…", len(non_image_indices))
        results = await asyncio.gather(*extract_tasks, return_exceptions=True)
        for i_pos, i_0based in enumerate(non_image_indices):
            result = results[i_pos]
            extractions_all[i_0based + 1] = result if not isinstance(result, Exception) else {}

    # Build embedding texts and generate embeddings
    embedding_texts: list[str] = []
    embedding_idx_map: list[int] = []  # maps embedding row → 0-based file index
    for i in non_image_indices:
        idx_1based = i + 1
        extr = extractions_all.get(idx_1based, {})
        text = build_embedding_text(files[i].path, extr)
        embedding_texts.append(text)
        embedding_idx_map.append(i)

    all_embeddings: np.ndarray | None = None
    embedding_idx_reverse: dict[int, int] = {}  # 0-based file index → embedding row (O(1) lookup)
    if embedding_texts:
        logger.info("Stage-0: generating embeddings for %d files…", len(embedding_texts))
        all_embeddings = embed_texts(embedding_texts)
        embedding_idx_reverse = {v: i for i, v in enumerate(embedding_idx_map)}
        logger.info("Stage-0: embeddings generated, shape=%s", all_embeddings.shape)

    _set_progress(request_id, int(n * 0.05), n, "内容提取完成",
                  f"已提取 {len(extractions_all)} 个文件内容，生成语义向量完成")

    # ── Stage 1: identify projects via all filenames ─────────────────────────────
    _check_cancelled(request_id)
    _set_progress(request_id, int(n * 0.05), n, "第一阶段", "AI 正在识别项目分组…")

    # Build compact file list with directory paths.
    # Token budget: ~100K chars ≈ 25K tokens (safe for most 128K+ context models).
    # If file list exceeds this, sample by directory to stay within budget.
    MAX_S1_CHARS = 100_000  # ~25K tokens, leaves room for system prompt + response

    compact = _build_compact_list(files)   # no indices → all files

    if len(compact) > MAX_S1_CHARS:
        # Too large — sample files per directory to fit within token budget
        logger.warning("Stage-1 file list too long (%d chars > %d), sampling by directory…",
                       len(compact), MAX_S1_CHARS)
        compact, sampled_count = _sample_compact_list_by_dir(files, MAX_S1_CHARS)
        user_s1 = (
            f"以下是文件夹中 {n} 个文件的代表性样本（{sampled_count} 个，按目录均匀采样），"
            f"请按项目/课题维度识别分组：\n\n{compact}"
        )
    else:
        user_s1 = (
            f"以下是文件夹中全部 {n} 个文件，"
            f"请按项目/课题维度识别分组：\n\n{compact}"
        )

    project_keywords: dict[str, list[str]] = {}
    try:
        # Try up to 2 times — retry if AI returns type-based grouping
        for _s1_attempt in range(2):
            raw_s1           = await _call_ai(client, ai_config.model, SYSTEM_PROMPT_STAGE1, user_s1)
            project_keywords = _parse_stage1_projects(raw_s1)
            if not project_keywords:
                raise ValueError("AI returned empty project list")

            # Filter out file extension keywords (py, pdf, xlsx, etc.)
            project_keywords = _filter_extension_keywords(project_keywords)

            # Detect type-based grouping and retry with stronger warning
            if _is_type_based_grouping(project_keywords) and _s1_attempt == 0:
                logger.warning("Stage-1 attempt %d returned type-based grouping, retrying with directory-first fallback…",
                               _s1_attempt + 1)
                # On retry, prepend a strong correction to the user message
                user_s1 = (
                    "⚠️ 上一次你按文件类型分组了（编程脚本/文档资料/图片素材），这是严重错误！\n"
                    "请重新分析，必须按【项目/竞赛/课题】分组。重点看每个文件的「目录」信息。\n\n"
                    + user_s1
                )
                continue
            break

        # If still type-based after retry, fall through to directory-based fallback
        if _is_type_based_grouping(project_keywords):
            logger.warning("Stage-1 still type-based after retry, using directory-based fallback")
            project_keywords = _directory_based_fallback(files)

        groups, uncertain_1based = _assign_by_keywords(files, project_keywords)
        # Merge micro-groups that share the same top-level directory
        groups = _merge_groups_by_top_dir(files, groups)
        # Absorb tiny groups (< 10 files) into the nearest large group
        groups = _absorb_tiny_groups(files, groups)
        # Time-cluster rescue: uncertain files whose mtime is close to confirmed files
        groups, uncertain_1based = _time_cluster_rescue(files, groups, uncertain_1based)
        logger.info("Stage-1 OK: %d projects identified: %s; %d uncertain files (after time-cluster)",
                    len(project_keywords), list(project_keywords.keys()), len(uncertain_1based))

        # ── Re-discovery: if too many files are uncertain, ask AI to find missed projects ──
        uncertain_ratio = len(uncertain_1based) / n if n > 0 else 0
        if uncertain_1based and uncertain_ratio > REDISCOVER_THRESHOLD:
            _set_progress(request_id, int(n * 0.12), n, "二次发现",
                          f"{len(uncertain_1based)} 个文件未匹配（{uncertain_ratio:.0%}），正在发现遗漏项目…")
            try:
                existing_names = "、".join(f"「{p}」" for p in project_keywords.keys())
                rediscover_prompt = SYSTEM_PROMPT_REDISCOVER.replace(
                    "{existing_projects}", existing_names)
                uncertain_0based = [i - 1 for i in uncertain_1based]
                compact_uncertain = _build_compact_list(files, uncertain_0based)
                user_rediscover = (
                    f"以下 {len(uncertain_1based)} 个文件在第一轮未被分配到任何项目，"
                    f"请识别其中可能被遗漏的项目：\n\n{compact_uncertain}"
                )
                raw_rediscover = await _call_ai(client, ai_config.model,
                                                rediscover_prompt, user_rediscover)
                new_projects = _parse_stage1_projects(raw_rediscover)
                if new_projects:
                    logger.info("Re-discovery found %d new projects: %s",
                                len(new_projects), list(new_projects.keys()))
                    # Merge new project keywords
                    project_keywords.update(new_projects)
                    # Re-run keyword matching on uncertain files only
                    uncertain_files_subset = [files[i - 1] for i in uncertain_1based]
                    sub_groups, _ = _assign_by_keywords(
                        uncertain_files_subset, new_projects)
                    # Map sub indices back to original 1-based indices
                    rescued = set()
                    for proj, sub_idxs in sub_groups.items():
                        if proj == "待分类":
                            continue
                        for si in sub_idxs:
                            original_idx = uncertain_1based[si - 1]
                            groups.setdefault(proj, []).append(original_idx)
                            rescued.add(original_idx)
                    # Remove rescued files from "待分类"
                    if "待分类" in groups:
                        groups["待分类"] = [i for i in groups["待分类"] if i not in rescued]
                        if not groups["待分类"]:
                            del groups["待分类"]
                    # Update uncertain list
                    uncertain_1based = [i for i in uncertain_1based if i not in rescued]
                    logger.info("Re-discovery rescued %d files; %d uncertain remain",
                                len(rescued), len(uncertain_1based))
            except Exception as e_rd:
                logger.warning("Re-discovery failed: %s — continuing with original groups", e_rd)

    except Exception as e:
        logger.warning("Stage-1 failed: %s — using token-based fallback", e)
        groups = _token_fallback_groups(files)
        uncertain_1based = []

    # ── Embedding rescue: assign uncertain files by cosine similarity to group centroids ──
    if uncertain_1based and all_embeddings is not None and embedding_idx_reverse:
        # Build centroids for each confirmed group
        confirmed_proj_emb_rows: dict[str, list[int]] = {}
        for proj_name, proj_indices in groups.items():
            if proj_name in ("待分类", "其他"):
                continue
            rows = [embedding_idx_reverse[idx - 1] for idx in proj_indices
                    if (idx - 1) in embedding_idx_reverse]
            if rows:
                confirmed_proj_emb_rows[proj_name] = rows

        if confirmed_proj_emb_rows:
            proj_centroids = compute_centroids(all_embeddings, confirmed_proj_emb_rows)
            emb_rescued: dict[int, str] = {}
            still_uncertain: list[int] = []
            EMB_RESCUE_THRESHOLD = 0.40

            for idx_1based in uncertain_1based:
                idx_0based = idx_1based - 1
                if idx_0based not in embedding_idx_reverse:
                    still_uncertain.append(idx_1based)
                    continue
                emb_row = embedding_idx_reverse[idx_0based]
                file_emb = all_embeddings[emb_row]
                # Find nearest centroid
                best_proj = None
                best_sim = -1.0
                for proj_name, centroid in proj_centroids.items():
                    sim = float(np.dot(file_emb, centroid))
                    if sim > best_sim:
                        best_sim = sim
                        best_proj = proj_name
                if best_proj and best_sim >= EMB_RESCUE_THRESHOLD:
                    emb_rescued[idx_1based] = best_proj
                else:
                    still_uncertain.append(idx_1based)

            if emb_rescued:
                for idx, proj in emb_rescued.items():
                    groups.setdefault(proj, []).append(idx)
                # Remove rescued from "待分类"
                if "待分类" in groups:
                    rescued_set = set(emb_rescued.keys())
                    groups["待分类"] = [i for i in groups["待分类"] if i not in rescued_set]
                    if not groups["待分类"]:
                        del groups["待分类"]
                logger.info("Embedding rescue: %d files rescued (threshold=%.2f); %d still uncertain",
                            len(emb_rescued), EMB_RESCUE_THRESHOLD, len(still_uncertain))
            uncertain_1based = still_uncertain

    # Handle files unassigned by Stage-1 (shouldn't happen, but be safe)
    all_assigned_s1 = {idx for idxs in groups.values() for idx in idxs}
    unassigned_s1   = [i for i in range(1, n + 1) if i not in all_assigned_s1]
    if unassigned_s1:
        groups.setdefault("其他", []).extend(unassigned_s1)

    # ── Diagnostic logging ────────────────────────────────────────────────────
    for gname, gidxs in sorted(groups.items(), key=lambda x: -len(x[1])):
        logger.info("  Group %-20s: %d files", gname, len(gidxs))
    logger.info("  Uncertain (待分类): %d files", len(uncertain_1based))

    group_names  = list(groups.keys())
    total_groups = len(group_names)
    _set_progress(
        request_id, n // 5, n,
        "第一阶段完成",
        f"已识别 {total_groups} 个项目分组，正在细分子类…",
    )

    # ── Stage 2: sub-cluster each project group ───────────────────────────────────
    _check_cancelled(request_id)
    sem              = asyncio.Semaphore(5)
    # Reuse Stage-0 extractions; Stage-2 can add more if needed
    extractions_s2: dict[int, dict] = dict(extractions_all)
    completed_groups = 0
    completed_files  = n // 5   # 20% after stage 1

    async def process_group(l1_name: str, g_indices: list[int]) -> None:
        nonlocal completed_groups, completed_files
        async with sem:
            _check_cancelled(request_id)
            _set_progress(
                request_id, completed_files, n, "第二阶段",
                f"正在细分「{l1_name}」（{len(g_indices)} 个文件）…",
            )

            # For large groups (200+): use embedding clustering if available.
            # Cluster all files by content similarity, then AI names each cluster.
            # This eliminates the token limit bottleneck and handles vague filenames.
            if len(g_indices) > 200 and all_embeddings is not None:
                # Gather embeddings for this group
                group_emb_rows = []
                group_emb_to_idx = []  # maps local position → 1-based file idx
                for idx_1based in g_indices:
                    idx_0based = idx_1based - 1
                    if idx_0based in embedding_idx_reverse:
                        emb_row = embedding_idx_reverse[idx_0based]
                        group_emb_rows.append(emb_row)
                        group_emb_to_idx.append(idx_1based)

                if len(group_emb_rows) >= 10:
                    group_embeddings = all_embeddings[group_emb_rows]
                    clusters = cluster_embeddings(group_embeddings, min_cluster_size=5, max_clusters=8)

                    # Remove noise cluster (-1) — assign noise files later
                    real_clusters = {k: v for k, v in clusters.items() if k != -1}
                    noise_local = clusters.get(-1, [])

                    if len(real_clusters) >= 2:
                        # Build representative file descriptions for AI naming
                        cluster_descriptions = []
                        for cid, local_indices in sorted(real_clusters.items()):
                            reps = get_representative_indices(group_embeddings, local_indices, n_representatives=5)
                            rep_lines = []
                            for local_i in reps:
                                idx_1based = group_emb_to_idx[local_i]
                                f = files[idx_1based - 1]
                                name = Path(f.path).name
                                parent = Path(f.path).parent.name or ""
                                gparent = Path(f.path).parent.parent.name if len(Path(f.path).parts) > 2 else ""
                                dir_ctx = f"{gparent}/{parent}" if gparent else parent
                                extr = extractions_all.get(idx_1based, {})
                                meta = extr.get("metadata", {}) if isinstance(extr, dict) else {}
                                title = (meta.get("title") or "").strip()
                                summary = (extr.get("summary_text") or "")[:200].replace("\n", " ")
                                parts = [f"  - {name}  (目录: {dir_ctx})"]
                                if title and title != name:
                                    parts.append(f"    标题：{title}")
                                if summary:
                                    parts.append(f"    内容：{summary}")
                                rep_lines.append("\n".join(parts))
                            cluster_descriptions.append(
                                f"簇 {cid}（{len(local_indices)} 个文件）：\n" + "\n".join(rep_lines)
                            )

                        user_naming = (
                            f'分组「{l1_name}」共 {len(g_indices)} 个文件，'
                            f'已自动聚类为 {len(real_clusters)} 个子簇。\n'
                            f'请为每个簇命名：\n\n' + "\n\n".join(cluster_descriptions)
                        )

                        try:
                            raw_names = await _call_ai(client, ai_config.model,
                                                       SYSTEM_PROMPT_NAME_CLUSTERS, user_naming)
                            data = _safe_json(raw_names)
                            names_map = data.get("names", {})

                            # Assign files by cluster
                            subs: dict[str, list[int]] = {}
                            for cid, local_indices in real_clusters.items():
                                sub_name = names_map.get(str(cid), f"子类{cid+1}")
                                for local_i in local_indices:
                                    idx_1based = group_emb_to_idx[local_i]
                                    assignments_by_idx[idx_1based] = [l1_name, sub_name]
                                subs[sub_name] = [group_emb_to_idx[li] for li in local_indices]

                            # Assign noise files to nearest cluster
                            if noise_local and subs:
                                cluster_centroids = compute_centroids(
                                    group_embeddings,
                                    {str(cid): idxs for cid, idxs in real_clusters.items()}
                                )
                                cid_to_name = {str(cid): names_map.get(str(cid), f"子类{cid+1}")
                                               for cid in real_clusters}
                                noise_embs = group_embeddings[noise_local]
                                noise_assigns = assign_to_nearest(noise_embs, cluster_centroids, threshold=0.0)
                                for i, (best_cid, _) in enumerate(noise_assigns):
                                    idx_1based = group_emb_to_idx[noise_local[i]]
                                    sub_name = cid_to_name.get(best_cid, next(iter(subs.keys())))
                                    assignments_by_idx[idx_1based] = [l1_name, sub_name]

                            # Assign files without embeddings to nearest sub-group by filename
                            no_emb_indices = [idx for idx in g_indices if idx not in {group_emb_to_idx[li] for li in range(len(group_emb_to_idx))}]
                            if no_emb_indices and subs:
                                matches = _match_to_best_subgroup(files, no_emb_indices, subs,
                                                                   all_embeddings, embedding_idx_reverse)
                                for idx, sub_name in matches.items():
                                    assignments_by_idx[idx] = [l1_name, sub_name]

                            logger.info("Stage-2 embedding cluster '%s': %d files → %d sub-clusters: %s",
                                        l1_name, len(g_indices), len(subs), list(subs.keys()))

                            completed_groups += 1
                            completed_files = int(n * 0.2 + n * 0.75 * completed_groups / total_groups)
                            _set_progress(request_id, completed_files, n, "第二阶段",
                                          f"已完成 {completed_groups} / {total_groups} 个分组…")
                            return

                        except Exception as e:
                            logger.warning("Stage-2 embedding naming failed for '%s': %s, falling back to filename-based", l1_name, e)

                # Fallback: filename-based approach for large groups without good embeddings
                sample = g_indices
                compact_0based = [idx - 1 for idx in g_indices]
                batch_size = min(80, len(g_indices))
                if len(g_indices) > batch_size:
                    step = len(compact_0based) // batch_size
                    sampled_0based = compact_0based[::step][:batch_size]
                else:
                    sampled_0based = compact_0based[:batch_size]
                sampled_compact = _build_compact_list(files, sampled_0based)
                logger.info("Stage-2 large group '%s' (fallback): %d total, batch %d", l1_name, len(g_indices), len(sampled_0based))
                user_s2 = (
                    f'分组「{l1_name}」共 {len(g_indices)} 个文件，'
                    f'以下是代表性样本（{len(sampled_0based)} 个），'
                    f'请细分为 2-8 个子类：\n\n{sampled_compact}'
                )

            elif len(g_indices) > 200:
                # Large group but no embeddings — original filename-based approach
                sample = g_indices
                compact_0based = [idx - 1 for idx in g_indices]
                batch_size = min(80, len(g_indices))
                if len(g_indices) > batch_size:
                    step = len(compact_0based) // batch_size
                    sampled_0based = compact_0based[::step][:batch_size]
                else:
                    sampled_0based = compact_0based[:batch_size]
                sampled_compact = _build_compact_list(files, sampled_0based)
                user_s2 = (
                    f'分组「{l1_name}」共 {len(g_indices)} 个文件，'
                    f'以下是代表性样本（{len(sampled_0based)} 个），'
                    f'请细分为 2-8 个子类：\n\n{sampled_compact}'
                )
            else:
                if len(g_indices) > MAX_S2_SAMPLE:
                    s_step = max(1, len(g_indices) // MAX_S2_SAMPLE)
                    sample = g_indices[::s_step][:MAX_S2_SAMPLE]
                else:
                    sample = g_indices

                # Lazy content extraction — run in thread pool to avoid blocking event loop
                extract_tasks   = [
                    asyncio.to_thread(extract, Path(files[idx - 1].path))
                    for idx in sample if idx not in extractions_s2
                ]
                extract_indices = [idx for idx in sample if idx not in extractions_s2]
                if extract_tasks:
                    extracted_results = await asyncio.gather(*extract_tasks, return_exceptions=True)
                    for idx, result in zip(extract_indices, extracted_results):
                        extractions_s2[idx] = result if not isinstance(result, Exception) else {}

                file_list = _build_content_list(files, sample, extractions_s2)
                note = (
                    f"（代表性样本 {len(sample)}/{len(g_indices)} 个）"
                    if len(sample) < len(g_indices) else ""
                )
                user_s2 = (
                    f'项目「{l1_name}」{note}共 {len(g_indices)} 个文件，'
                    f'请按子主题/子阶段细分：\n\n{file_list}'
                )

            try:
                raw_s2 = await _call_ai(client, ai_config.model, SYSTEM_PROMPT_STAGE2, user_s2)
                subs   = _parse_subgroups(raw_s2, set(sample))

                if not subs:
                    # AI returned empty/invalid — keep all files under l1_name
                    logger.warning("Stage-2 returned empty subgroups for '%s', keeping flat", l1_name)
                    for idx in g_indices:
                        assignments_by_idx[idx] = [l1_name, l1_name]
                else:
                    assigned_here: set[int] = set()
                    for l2_name, s_indices in subs.items():
                        for idx in s_indices:
                            assignments_by_idx[idx] = [l1_name, l2_name]
                            assigned_here.add(idx)

                    # Non-sampled files → match to closest sub-group by filename
                    unassigned = [idx for idx in g_indices if idx not in assigned_here]
                    if unassigned:
                        matches = _match_to_best_subgroup(files, unassigned, subs,
                                                           all_embeddings, embedding_idx_reverse)
                        for idx, sub_name in matches.items():
                            assignments_by_idx[idx] = [l1_name, sub_name]

            except Exception as e:
                logger.warning("Stage-2 sub-cluster failed for '%s': %s", l1_name, e)
                for idx in g_indices:
                    assignments_by_idx[idx] = [l1_name, l1_name]

            completed_groups += 1
            completed_files   = int(n * 0.2 + n * 0.75 * completed_groups / total_groups)
            _set_progress(
                request_id, completed_files, n, "第二阶段",
                f"已完成 {completed_groups} / {total_groups} 个分组…",
            )

    # Skip "待分类" — those files go to Layer 2 content fallback instead
    stage2_groups = {name: idxs for name, idxs in groups.items() if name not in ("待分类", "其他")}
    await asyncio.gather(*[process_group(name, idxs) for name, idxs in stage2_groups.items()])

    # ── Layer 2: content/filename fallback for ALL uncertain non-image files ─────
    uncertain_images_idx = [
        i for i in uncertain_1based
        if Path(files[i - 1].path).suffix.lower() in _IMAGE_EXTS
    ]
    uncertain_nonimage_idx = [
        i for i in uncertain_1based
        if Path(files[i - 1].path).suffix.lower() not in _IMAGE_EXTS
    ]

    # Use Stage-1 project names if available; otherwise fall back to group names
    project_names = list(project_keywords.keys()) if project_keywords else list(groups.keys())

    if uncertain_nonimage_idx and all_embeddings is not None:
        _set_progress(request_id, int(n * 0.95), n, "内容兜底",
                      f"正在通过语义向量分析 {len(uncertain_nonimage_idx)} 个未匹配文件…")

        # Build centroids from confirmed project groups (excluding 待分类/其他)
        confirmed_groups_0based: dict[str, list[int]] = {}
        for proj_name, proj_indices in groups.items():
            if proj_name in ("待分类", "其他"):
                continue
            indices_0based = []
            for idx_1based in proj_indices:
                if (idx_1based - 1) in embedding_idx_reverse:
                    emb_row = embedding_idx_reverse[idx_1based - 1]
                    indices_0based.append(emb_row)
            if indices_0based:
                confirmed_groups_0based[proj_name] = indices_0based

        layer2_results: dict[int, str] = {}

        if confirmed_groups_0based:
            centroids = compute_centroids(all_embeddings, confirmed_groups_0based)

            # Get embeddings for uncertain files
            uncertain_emb_rows = []
            uncertain_emb_to_1based = []
            for idx_1based in uncertain_nonimage_idx:
                idx_0based = idx_1based - 1
                if idx_0based in embedding_idx_reverse:
                    emb_row = embedding_idx_reverse[idx_0based]
                    uncertain_emb_rows.append(emb_row)
                    uncertain_emb_to_1based.append(idx_1based)

            if uncertain_emb_rows:
                uncertain_embeddings = all_embeddings[uncertain_emb_rows]
                assignments_list = assign_to_nearest(uncertain_embeddings, centroids, threshold=0.35)

                embedded_count = 0
                ai_fallback_files: list[tuple[int, ScanResult]] = []
                for i, (proj_name, sim) in enumerate(assignments_list):
                    idx_1based = uncertain_emb_to_1based[i]
                    if proj_name:
                        layer2_results[idx_1based] = proj_name
                        embedded_count += 1
                    else:
                        ai_fallback_files.append((idx_1based, files[idx_1based - 1]))

                logger.info("Layer-2 embedding: assigned %d/%d files; %d need AI fallback",
                            embedded_count, len(uncertain_emb_rows), len(ai_fallback_files))

                # AI fallback for files below similarity threshold
                if ai_fallback_files:
                    ai_results = await _classify_uncertain_by_content(
                        client, ai_config.model,
                        ai_fallback_files, project_names,
                        request_id, int(n * 0.96), n,
                    )
                    layer2_results.update(ai_results)

        # Files without embeddings also go through AI fallback
        no_emb_files = [
            (idx, files[idx - 1]) for idx in uncertain_nonimage_idx
            if idx not in layer2_results and (idx - 1) not in embedding_idx_reverse
        ]
        if no_emb_files:
            ai_results = await _classify_uncertain_by_content(
                client, ai_config.model,
                no_emb_files, project_names,
                request_id, int(n * 0.96), n,
            )
            layer2_results.update(ai_results)

        for idx, proj in layer2_results.items():
            assignments_by_idx[idx] = [proj, proj]

        # Run Stage 2 for newly assigned groups from Layer 2
        layer2_new_groups: dict[str, list[int]] = {}
        for idx, proj in layer2_results.items():
            if proj != "其他文件":
                layer2_new_groups.setdefault(proj, []).append(idx)
        if layer2_new_groups:
            logger.info("Layer-2 assigned %d files to %d groups, running Stage-2 sub-clustering",
                        sum(len(v) for v in layer2_new_groups.values()), len(layer2_new_groups))
            await asyncio.gather(*[
                process_group(name, idxs)
                for name, idxs in layer2_new_groups.items()
                if len(idxs) >= 2
            ])

    elif uncertain_nonimage_idx:
        # Fallback: no embeddings available, use pure AI
        _set_progress(request_id, int(n * 0.95), n, "内容兜底",
                      f"正在二次分析 {len(uncertain_nonimage_idx)} 个未匹配文件…")
        uncertain_nonimage_files = [(i, files[i - 1]) for i in uncertain_nonimage_idx]
        layer2_results = await _classify_uncertain_by_content(
            client, ai_config.model,
            uncertain_nonimage_files, project_names,
            request_id, int(n * 0.95), n,
        )
        for idx, proj in layer2_results.items():
            assignments_by_idx[idx] = [proj, proj]

    # ── Layer A/B/C: image classification ─────────────────────────────────────────
    if uncertain_images_idx:
        text_assignments_for_coloc = {
            i: v for i, v in assignments_by_idx.items()
            if Path(files[i - 1].path).suffix.lower() not in _IMAGE_EXTS
        }
        image_results = await _classify_images(
            client, ai_config.model,
            uncertain_images_idx, files,
            text_assignments_for_coloc, project_names,
            request_id, int(n * 0.97), n,
        )
        for idx, (l1, l2) in image_results.items():
            assignments_by_idx[idx] = [l1, l2]

    # ── Fill any remaining unassigned files ───────────────────────────────────────
    still_unassigned = [i for i in range(1, n + 1) if i not in assignments_by_idx]
    if still_unassigned:
        logger.info("Final fallback: %d files still unassigned → '其他文件'", len(still_unassigned))
        for i in still_unassigned:
            assignments_by_idx[i] = ["其他文件", "未归类文件"]

    # ── Final distribution diagnostic ────────────────────────────────────────────
    from collections import Counter as _FinalCounter
    l1_counts = _FinalCounter(segs[0] for segs in assignments_by_idx.values())
    logger.info("Final L1 distribution (before recursive split):")
    for l1_name, cnt in l1_counts.most_common():
        logger.info("  %-25s: %d files (%.0f%%)", l1_name, cnt, cnt / n * 100)

    # ── Stage 3: recursive subdivision of large leaf folders ──────────────────────
    _set_progress(request_id, int(n * 0.98), n, "递归细分", "正在细分过大的子文件夹…")
    await _recursive_subdivide_all(
        client, ai_config.model, files, assignments_by_idx, extractions_s2,
        request_id, n,
        all_embeddings=all_embeddings,
        embedding_idx_map=embedding_idx_map,
        embedding_idx_reverse=embedding_idx_reverse,
    )

    _set_progress(request_id, n, n, "完成", "正在整理结果…")

    # ── Build recursive tree output ───────────────────────────────────────────────
    # tree is a recursive dict: each node = { "files": [...], "children": { name: node } }
    def _empty_node() -> dict:
        return {"files": [], "children": {}}

    tree_root: dict = _empty_node()
    assignments: dict[str, dict] = {}

    for idx, path_segments in assignments_by_idx.items():
        path = files[idx - 1].path
        node = tree_root
        for seg in path_segments:
            if seg not in node["children"]:
                node["children"][seg] = _empty_node()
            node = node["children"][seg]
        node["files"].append(path)
        assignments[path] = {"sub_path": path_segments}

    # uncertain_paths: non-image files that went through Layer-2 fallback.
    uncertain_paths = [files[i - 1].path for i in uncertain_nonimage_idx]

    # ── Back-fill dev-artifact files into their parent project group ──────────
    # Dev artifacts were excluded from classification. Now assign each one to
    # the same L1 group as the majority of real files from the same top-level
    # directory, with a special "开发依赖" L2 sub-group.
    if dev_artifact_indices:
        # Build mapping: top-level dir → most common L1 group
        top_dir_to_l1: dict[str, Counter] = {}
        for idx_1based, path_segs in assignments_by_idx.items():
            orig_idx = real_to_original[idx_1based - 1]
            f_path = Path(original_files[orig_idx].path)
            try:
                rel = f_path.relative_to(common_root_pre)
                top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            except ValueError:
                top = "(root)"
            l1 = path_segs[0] if path_segs else "其他"
            top_dir_to_l1.setdefault(top, Counter())[l1] += 1

        top_dir_best_l1: dict[str, str] = {}
        for td, counter in top_dir_to_l1.items():
            top_dir_best_l1[td] = counter.most_common(1)[0][0]

        dev_assigned = 0
        for orig_idx in dev_artifact_indices:
            f = original_files[orig_idx]
            f_path = Path(f.path)
            try:
                rel = f_path.relative_to(common_root_pre)
                top = rel.parts[0] if len(rel.parts) > 1 else "(root)"
            except ValueError:
                top = "(root)"
            l1 = top_dir_best_l1.get(top)
            if not l1:
                # Fallback: largest L1 group
                l1 = max(tree_root["children"].keys(),
                         key=lambda k: len(tree_root["children"][k].get("files", [])),
                         default="其他")
            l2 = "开发依赖"
            # Add to tree
            if l1 not in tree_root["children"]:
                tree_root["children"][l1] = _empty_node()
            l1_node = tree_root["children"][l1]
            if l2 not in l1_node["children"]:
                l1_node["children"][l2] = _empty_node()
            l1_node["children"][l2]["files"].append(f.path)
            assignments[f.path] = {"sub_path": [l1, l2]}
            dev_assigned += 1

        logger.info("Back-filled %d dev-artifact files into project groups", dev_assigned)

    return {"tree": tree_root["children"], "assignments": assignments, "uncertain_paths": uncertain_paths}
