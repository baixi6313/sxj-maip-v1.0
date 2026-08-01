# -*- coding: utf-8 -*-
"""构建《事现鉴：多智能体交互协议 v1.0》自包含转发门户 index.html。
- 将 SXJ-MAIP-v1.0.md 渲染为 HTML（含目录/表格/代码块）
- 页眉/页脚显著署名起草/汇编者：WorkBuddy（AI 协作工程师）
- 含指纹(防篡改) + AI 回执模板
输出: sxj-verify/maip-portal/index.html
"""
import os, re
import markdown

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, "SXJ-MAIP-v1.0.md")
SHA = os.path.join(ROOT, "SXJ-MAIP-v1.0.sha256")
OUT_DIR = os.path.join(ROOT, "maip-portal")
os.makedirs(OUT_DIR, exist_ok=True)

md_text = open(SRC, "r", encoding="utf-8").read()
# 提取指纹
sha_lines = open(SHA, "r", encoding="utf-8").read()
m_doc = re.search(r"([0-9a-f]{64})\s+SXJ-MAIP-v1\.0\.md", sha_lines)
m_all = re.search(r"([0-9a-f]{64})", sha_lines.split("# 协议套件合并指纹")[1] if "# 协议套件合并指纹" in sha_lines else "")
doc_sha = m_doc.group(1) if m_doc else "unknown"
all_sha = m_all.group(1) if m_all else "unknown"

# 渲染：前置 [TOC] 生成目录
body_html = markdown.markdown(
    "[TOC]\n\n" + md_text,
    extensions=["tables", "fenced_code", "toc", "sane_lists", "attr_list"],
    extension_configs={"toc": {"permalink": False}},
)

AUTHOR = "WorkBuddy（AI 协作工程师）"
DATE = "2026-08-02"
GH_REPO = "baixi6313/sxj-maip-v1.0"
GH_URL = f"https://github.com/{GH_REPO}"

receipt_tpl = '''{
  "maip_version": "SXJ-MAIP/1.0",
  "msg_id": "<uuid>",
  "ledger_sha256": "''' + doc_sha + '''",
  "agent_id": "你的名字(如 DeepSeek / 元宝 / Kimi / 豆包 / DuMate)",
  "role": "VER-FACT | VER-TECH | VER-NORM | CHAL | COLD | HOT",
  "type": "POSITION",
  "case_id": "case_XXX",
  "verdict": "PASS | FAIL | CONDITIONAL | UNKNOWN",
  "confidence": 0.0,            // 0~1；AI 演绎(E4)硬顶 0.5 且不计入加权
  "evidence_grade": "E1|E2|E3|E4",
  "evidence_refs": ["来源链接/文件"],
  "statement": "你的立场与理由（须可被证伪）",
  "reserved_for_adjudication": "",  // 触及 R-1..R-6 时必填，AI 不得给 PASS/FAIL
  "prev_hash": "<上一条消息哈希>",
  "hash": "<本消息哈希>",
  "signature": "<自证身份字符串>"
}'''

PAGE = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>事现鉴：多智能体交互协议 v1.0 (SXJ-MAIP/1.0)</title>
<style>
  :root {{ --blue:#2F6FED; --gold:#C9A24B; --red:#A32D2D; --ink:#1a1a1a; --bg:#f5f3ee; --card:#fff; --line:#e4e0d8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink); font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; line-height:1.75; }}
  header {{ background:linear-gradient(135deg,var(--blue),#1d4fb0); color:#fff; padding:30px 22px 26px; }}
  header .kicker {{ letter-spacing:2px; font-size:12px; opacity:.85; }}
  header h1 {{ margin:6px 0 12px; font-size:24px; }}
  header .meta {{ font-size:13px; opacity:.95; }}
  header .meta code {{ background:rgba(255,255,255,.15); padding:1px 6px; border-radius:4px; font-size:12px; word-break:break-all; }}
  .badge {{ display:inline-block; background:var(--gold); color:#3a2c00; border-radius:4px; padding:1px 9px; font-size:12px; font-weight:600; }}
  main {{ max-width:960px; margin:0 auto; padding:20px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px 22px; margin:16px 0; box-shadow:0 1px 3px rgba(0,0,0,.04); }}
  .card h2 {{ color:var(--blue); font-size:19px; border-left:4px solid var(--gold); padding-left:10px; margin-top:0; }}
  .cover p {{ font-size:14.5px; }}
  .warn {{ background:#fff4e6; border:1px solid #ffd8a8; border-radius:8px; padding:11px 15px; color:#7a4b00; font-size:13.5px; }}
  .content {{ font-size:14.5px; }}
  .content h1, .content h2, .content h3 {{ color:var(--ink); line-height:1.4; }}
  .content h1 {{ font-size:22px; border-bottom:2px solid var(--gold); padding-bottom:6px; margin-top:28px; }}
  .content h2 {{ font-size:18px; margin-top:24px; color:var(--blue); }}
  .content h3 {{ font-size:15.5px; margin-top:18px; }}
  .content code {{ background:#eef1f8; color:#1d4fb0; padding:1px 5px; border-radius:4px; font-size:13px; }}
  .content pre {{ background:#1e1e1e; color:#e6e6e6; padding:14px; border-radius:8px; overflow:auto; font-size:12.5px; }}
  .content pre code {{ background:none; color:inherit; padding:0; }}
  .content table {{ border-collapse:collapse; width:100%; margin:12px 0; font-size:13.5px; }}
  .content th, .content td {{ border:1px solid var(--line); padding:7px 10px; text-align:left; }}
  .content th {{ background:#eef1f8; }}
  .content blockquote {{ border-left:4px solid var(--gold); margin:12px 0; padding:6px 14px; color:#555; background:#faf8f2; }}
  .toc {{ background:#faf8f2; }}
  .toc ul {{ list-style:none; padding-left:0; columns:2; }}
  .toc li {{ font-size:13px; margin:3px 0; }}
  .toc a {{ color:var(--blue); text-decoration:none; }}
  .toolbar {{ display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; }}
  button {{ background:var(--blue); color:#fff; border:0; border-radius:8px; padding:8px 14px; cursor:pointer; font-size:13px; }}
  button.alt {{ background:var(--gold); color:#3a2c00; }}
  footer {{ text-align:center; color:#888; font-size:12.5px; padding:26px 16px; line-height:1.9; }}
  footer a {{ color:var(--blue); }}
  footer code {{ background:#eee; padding:1px 5px; border-radius:4px; word-break:break-all; }}
</style>
</head>
<body>
<header>
  <div class="kicker">SXJ-MAIP / 1.0</div>
  <h1>事现鉴：多智能体交互协议 v1.0</h1>
  <div class="meta">
    起草 / 汇编：<b>{AUTHOR}</b>　·　日期 {DATE}<br>
    状态：<span class="badge">DRAFT · 待决定层（白玺）批准</span><br>
    协议指纹 SHA256：<code>{doc_sha}</code><br>
    套件合并指纹：<code>{all_sha}</code>
  </div>
</header>
<main>

<div class="card cover">
  <h2>这是什么 / 给谁看</h2>
  <p>这是一份<b>机器可读的多智能体交互协议</b>：规定多家 AI 如何就"某条事实是否可验证"进行轮值质疑、盲评、加权收敛，
  同时把<b>哪些事只有人类能拍板</b>写死为保留事项。它把前几轮口头交互规则"协议化"，并用程序卡死（任何改动都可被哈希自洽校验发现）。</p>
  <p class="warn"><b>裁决权归属：</b>本协议的<b>最终裁定权</b>属于人类决定层（白玺）。AI（含本页起草者 {AUTHOR}）仅负责起草、汇编与机器校验，
  <b>不得</b>对 §10.1 所列保留事项（R-1~R-6）给出 PASS/FAIL 终局结论；AI 至多可输出 CONDITIONAL（咨询性建议）或 UNKNOWN，并须填 <code>reserved_for_adjudication</code>。</p>
  <p>转发此页即等同转发整份协议正文 + 指纹 + 回执模板，无需再附其他文件。</p>
</div>

<article class="card content">
{body_html}
</article>

<div class="card">
  <h2>AI 回执模板（可选）</h2>
  <p>如你（任一参与 AI）愿按本协议参与验证，可将下方 JSON 回填并交回中转方。完整信封字段见协议第 6 章。</p>
  <div class="toolbar"><button onclick="copyReceipt()">复制回执模板</button></div>
  <pre id="receipt">{receipt_tpl}</pre>
  <p class="warn">注意：<code>ledger_sha256</code> 须与本页指纹一致（{doc_sha[:16]}…），否则中转方会拒收（防篡改 / 防版本错位）。</p>
</div>

</main>
<footer>
  本文档由 <b>{AUTHOR}</b> 起草与汇编 · {DATE}<br>
  源文件、JSON Schema、样例一轮与零依赖校验器见 GitHub：<a href="{GH_URL}">{GH_REPO}</a><br>
  协议指纹 SHA256：<code>{doc_sha}</code><br>
  <span style="color:#aaa">本页为自包含静态文件，可离线打开；转发链接由 CloudStudio / GitHub Pages 托管。</span>
</footer>
<script>
function copyReceipt(){{ const t=document.getElementById('receipt').innerText; navigator.clipboard.writeText(t).then(()=>alert('回执模板已复制')); }}
</script>
</body>
</html>'''

out = os.path.join(OUT_DIR, "index.html")
open(out, "w", encoding="utf-8").write(PAGE)
print("WROTE", out, len(PAGE), "bytes")
print("AUTHOR:", AUTHOR)
print("DOC_SHA:", doc_sha)
print("ALL_SHA:", all_sha)
