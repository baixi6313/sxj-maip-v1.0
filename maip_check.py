#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
maip_check.py —— 事现鉴·多智能体交互协议 v1.0 参考实现（校验器）

大白话：这是「开会规矩」的裁判。你把一轮交互的消息记录喂给它，
它会逐条检查有没有违规、这一轮算不算数、能不能进入下一状态。

零依赖，只用 Python 标准库。任何外部平台 agent 都能直接跑。

用法：
    python maip_check.py maip-example-round.json            # 校验
    python maip_check.py maip-example-round.json --fill      # 计算并回填哈希链 + 重算收敛报告
    python maip_check.py maip-example-round.json --json      # 机器可读输出

退出码：0=通过（可进入下一状态）；1=有 MUST 违规；2=文件/格式错误
"""

import json
import sys
import hashlib
from pathlib import Path

MAIP_VERSION = "1.0"
DEFAULT_THETA = 0.75
MIN_PARTICIPANTS_BFT = 4          # §9.1 n >= 3f+1，f>=1 需要 n>=4
COLD_RELEASE_THRESHOLD = 2        # §9.2 发布门槛
VER_ROLES = ("VER-TECH", "VER-FACT", "VER-NORM")

# §3.2 行为契约：角色 -> 可发出的消息类型
EMIT_WHITELIST = {
    "ORC":       {"CALL", "CONVERGENCE_REPORT", "SUSPEND"},
    "ORC-EVT":   {"CALL", "CONVERGENCE_REPORT", "SUSPEND"},
    "ORC-VAL":   {"CALL", "CONVERGENCE_REPORT", "SUSPEND"},
    "ORC-EXT":   {"CALL", "CONVERGENCE_REPORT", "SUSPEND", "BAIT_PROBE", "BAIT_RESULT"},
    "VER-TECH":  {"POSITION", "CHALLENGE", "REBUTTAL"},
    "VER-FACT":  {"POSITION", "CHALLENGE", "REBUTTAL"},
    "VER-NORM":  {"POSITION", "CHALLENGE", "REBUTTAL"},
    "CHAL":      {"CHALLENGE"},
    "COLD":      {"POSITION", "RECEIPT"},
    "HOT":       {"POSITION", "RECEIPT"},
    "ADJ":       {"ADJUDICATION", "SUSPEND"},
    "REC":       {"RECEIPT"},
}

BASE_WEIGHT = {"COLD": 1.0, "HOT": 0.5, "HUMAN": 0.0}
CHALLENGE_TYPES = {"EVIDENCE_GAP", "LOGIC_FLAW", "SCOPE_CREEP", "ROLE_BREACH", "CONTRADICTION"}
VERDICTS = {"PASS", "CONDITIONAL", "FAIL", "UNKNOWN"}
GRADES = {"E1", "E2", "E3", "E4"}


class Report:
    def __init__(self):
        self.violations = []   # MUST 违规 -> 阻断
        self.warnings = []     # SHOULD 瑕疵 / 提示
        self.info = []

    def v(self, code, msg):
        self.violations.append({"code": code, "msg": msg})

    def w(self, code, msg):
        self.warnings.append({"code": code, "msg": msg})

    def i(self, msg):
        self.info.append(msg)

    @property
    def ok(self):
        return not self.violations


def canonical(obj):
    """规范化 JSON：排序键、无多余空白、UTF-8 不转义。用于哈希可复现。"""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def msg_hash(msg):
    """§4.1 hash = SHA-256(除 hash/signature 外字段的规范化 JSON)"""
    body = {k: v for k, v in msg.items() if k not in ("hash", "signature")}
    return hashlib.sha256(canonical(body).encode("utf-8")).hexdigest()


def msg_signature(msg):
    """§4.1 signature = SHA-256(agent_id + msg_id + hash) 前 16 位"""
    raw = msg["from"]["agent_id"] + msg["msg_id"] + msg["hash"]
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def fill_chain(messages):
    """回填 prev_hash -> hash -> signature 哈希链（§11.3）"""
    prev = None
    for m in messages:
        m["prev_hash"] = prev
        m["hash"] = msg_hash(m)
        m["signature"] = msg_signature(m)
        prev = m["hash"]
    return messages


# ---------------------------------------------------------------- 校验各章

def check_envelope(m, ledger_sha, rp):
    mid = m.get("msg_id", "<no-id>")

    if m.get("maip_version") != MAIP_VERSION:
        rp.v("L1", f"[{mid}] maip_version 不是 {MAIP_VERSION}")

    for f in ("msg_id", "msg_type", "case_id", "round", "from", "to",
              "issued_at", "ledger_sha256", "payload"):
        if f not in m:
            rp.v("L1", f"[{mid}] 缺必填信封字段 {f}")

    frm = m.get("from", {})
    role, tier = frm.get("role"), frm.get("tier")
    if role not in EMIT_WHITELIST:
        rp.v("L1", f"[{mid}] 未知角色 {role}")
    if tier not in BASE_WEIGHT:
        rp.v("L1", f"[{mid}] 未知层级 {tier}")

    # §3.3 L3 指纹错配
    if m.get("ledger_sha256") != ledger_sha:
        rp.v("L3", f"[{mid}] ledger_sha256 与本案档案指纹不符 → 拒收，该方本案 trust 归零")

    # §3.3 L2 越权
    if role in EMIT_WHITELIST and m.get("msg_type") not in EMIT_WHITELIST[role]:
        rp.v("L2", f"[{mid}] 角色 {role} 无权发出 {m.get('msg_type')} → 拒收 + trust×0.9")

    # §2.2(2) 编排者不投票
    if str(role).startswith("ORC") and m.get("msg_type") == "POSITION":
        rp.v("L2", f"[{mid}] 编排者不得发表 POSITION（§2.2）")

    # 哈希自洽（仅在已填充时校验）
    if m.get("hash"):
        if m["hash"] != msg_hash(m):
            rp.v("HASH", f"[{mid}] hash 与内容不符（内容被篡改或未重算）")
        elif m.get("signature") and m["signature"] != msg_signature(m):
            rp.v("HASH", f"[{mid}] signature 与 hash 不符")


def check_position(m, rp):
    mid = m["msg_id"]
    p = m.get("payload", {})

    verdict = p.get("verdict")
    if verdict not in VERDICTS:
        rp.v("L1", f"[{mid}] verdict 非法：{verdict}")

    # §6.3 置信度强制申报
    if "confidence" not in p:
        rp.v("L1", f"[{mid}] POSITION 缺 confidence → 无效（§6.3：无置信度的判定是无信息的）")
        return
    conf = p["confidence"]
    if not isinstance(conf, (int, float)) or not (0 <= conf <= 1):
        rp.v("L1", f"[{mid}] confidence 越界：{conf}")

    grade = p.get("evidence_grade")
    if grade not in GRADES:
        rp.v("L1", f"[{mid}] evidence_grade 非法：{grade}")

    refs = p.get("evidence_refs", [])
    if not refs and verdict != "UNKNOWN":
        rp.v("L1", f"[{mid}] 无 evidence_refs 时 verdict 必须为 UNKNOWN（§4.2.2）")

    # §4.2.2 E4（AI 演绎）置信度硬顶
    if grade == "E4" and conf > 0.5:
        rp.v("L1", f"[{mid}] evidence_grade=E4 时 confidence 必须 ≤0.50，实为 {conf}")

    # §10.1 保留事项：禁止 AI 给终局判定
    reserved = p.get("reserved_for_adjudication") or []
    if reserved and verdict in ("PASS", "FAIL"):
        rp.v("R", f"[{mid}] 触及保留事项仍给出终局 verdict={verdict}（§10.1 禁止；应为 UNKNOWN 或 CONDITIONAL）")


def check_challenge(m, rp):
    """§7.2 有效质疑判据。返回 True 表示这是一条有效质疑。"""
    mid = m["msg_id"]
    p = m.get("payload", {})
    valid = True

    for f in ("target_agent", "target_msg_id", "target_claim", "challenge_type", "grounds"):
        if not p.get(f):
            rp.v("L1", f"[{mid}] CHALLENGE 缺 {f} → 无效质疑（§7.2）")
            valid = False

    if p.get("challenge_type") not in CHALLENGE_TYPES:
        rp.v("L1", f"[{mid}] challenge_type 非法：{p.get('challenge_type')}")
        valid = False

    if len(str(p.get("target_claim", ""))) < 8:
        rp.v("L1", f"[{mid}] target_claim 过短，未引用被质疑方原文片段（§7.2）")
        valid = False

    if len(str(p.get("grounds", ""))) < 10:
        rp.v("L1", f"[{mid}] grounds 过短，疑为态度表达而非可证伪问题（§7.2）")
        valid = False

    if p.get("target_agent") == m["from"]["agent_id"]:
        rp.v("L1", f"[{mid}] 不得自我质疑")
        valid = False

    return valid


def check_rebuttal(m, rp):
    mid = m["msg_id"]
    p = m.get("payload", {})
    if not p.get("in_reply_to_challenge"):
        rp.v("L1", f"[{mid}] REBUTTAL 缺 in_reply_to_challenge")
    if p.get("response") not in ("ACCEPT", "PARTIAL", "REJECT"):
        rp.v("L1", f"[{mid}] response 非法：{p.get('response')}")
    rc = p.get("revised_confidence")
    if rc is not None and not (0 <= rc <= 1):
        rp.v("L1", f"[{mid}] revised_confidence 越界：{rc}")


# ---------------------------------------------------------------- 收敛计算

def compute_convergence(messages, theta, rp):
    """§6.2 权重计算 + §7.1 角色覆盖 + §9 容错，产出收敛报告 payload。"""
    positions = [m for m in messages if m["msg_type"] == "POSITION"]
    rebuttals = [m for m in messages if m["msg_type"] == "REBUTTAL"]
    challenges = [m for m in messages if m["msg_type"] == "CHALLENGE"]

    # 用答辩里的修正值覆盖原始立场
    revised = {}
    for r in rebuttals:
        tgt_challenge = r["payload"].get("in_reply_to_challenge")
        ch = next((c for c in challenges if c["msg_id"] == tgt_challenge), None)
        if ch:
            tgt_pos = ch["payload"].get("target_msg_id")
            revised[tgt_pos] = {
                "verdict": r["payload"].get("revised_verdict"),
                "confidence": r["payload"].get("revised_confidence"),
            }

    effective = []   # 计入加权的表态
    abstain = []
    reserved_items = []

    for p in positions:
        pid = p["msg_id"]
        pl = p["payload"]
        verdict = pl.get("verdict")
        conf = pl.get("confidence", 0)
        if pid in revised:
            if revised[pid]["verdict"]:
                verdict = revised[pid]["verdict"]
            if revised[pid]["confidence"] is not None:
                conf = revised[pid]["confidence"]

        reserved_items += (pl.get("reserved_for_adjudication") or [])

        base = BASE_WEIGHT.get(p["from"]["tier"], 0.0)
        grade = pl.get("evidence_grade")
        trust = 1.0   # v1.0 参考实现：trust 由外部状态文件维护，此处默认 1.0

        # abstain 条件：UNKNOWN / E4 演绎 / 权重为 0
        if verdict == "UNKNOWN" or grade == "E4" or base == 0.0:
            abstain.append({"msg_id": pid, "agent": p["from"]["agent_id"],
                            "verdict": verdict, "reason":
                            "UNKNOWN" if verdict == "UNKNOWN" else ("E4 演绎" if grade == "E4" else "权重 0")})
            continue

        effective.append({
            "msg_id": pid,
            "agent": p["from"]["agent_id"],
            "role": p["from"]["role"],
            "tier": p["from"]["tier"],
            "verdict": verdict,
            "confidence": conf,
            "weight": round(base * conf * trust, 4),
        })

    total_w = sum(e["weight"] for e in effective)
    tally = {}
    for e in effective:
        tally[e["verdict"]] = tally.get(e["verdict"], 0) + e["weight"]

    if total_w > 0:
        top_verdict = max(tally, key=tally.get)
        agreement = round(tally[top_verdict] / total_w, 4)
    else:
        top_verdict, agreement = None, 0.0

    # §7.1 三类互补角色覆盖
    roles_present = {r: any(p["from"]["role"] == r for p in positions) for r in VER_ROLES}
    role_all_fail = {}
    for r in VER_ROLES:
        rp_pos = [p for p in positions if p["from"]["role"] == r]
        role_all_fail[r] = bool(rp_pos) and all(p["payload"].get("verdict") == "FAIL" for p in rp_pos)

    participants = len({p["from"]["agent_id"] for p in positions})
    cold_count = len({p["from"]["agent_id"] for p in positions
                      if p["from"]["tier"] == "COLD"
                      and p["payload"].get("verdict") in ("PASS", "CONDITIONAL")})
    f_tol = max(0, (participants - 1) // 3)

    valid_challenges = [c for c in challenges if check_challenge(c, Report())]
    # low_adversariality：仅轮值方提出质疑
    call = next((m for m in messages if m["msg_type"] == "CALL"), None)
    designated = call["payload"].get("designated_challenger") if call else None
    low_adv = bool(valid_challenges) and all(
        c["from"]["agent_id"] == designated for c in valid_challenges)

    # ---- 门控判定 ----
    blocking = []

    if not valid_challenges:
        rp.v("S3", "本轮无有效质疑 → 本轮作废，强制重开并轮换质疑者（§5.2 S2→S3）")
        blocking.append("本轮无有效质疑")

    for r, present in roles_present.items():
        if not present:
            rp.v("S4", f"缺 {r} 角色表态 → 不得进入 S5_CONVERGED（§7.1）")
            blocking.append(f"缺 {r}")
        if role_all_fail[r]:
            rp.v("S4", f"{r} 角色全部 FAIL → 不得进入 S5_CONVERGED（§7.1）")
            blocking.append(f"{r} 全 FAIL")

    if participants < MIN_PARTICIPANTS_BFT:
        rp.v("S4", f"有效参与方 {participants} < {MIN_PARTICIPANTS_BFT} → 不满足 n≥3f+1 容错下限（§9.1）")
        blocking.append(f"参与方不足（{participants}/{MIN_PARTICIPANTS_BFT}）")

    if agreement < theta:
        rp.w("S4", f"加权一致度 {agreement} < 阈值 {theta} → 应进入下一轮（§5.2 S4→S2）")
        blocking.append(f"一致度未达阈值（{agreement}<{theta}）")

    if low_adv:
        rp.w("7.4", "仅轮值方提出质疑（low_adversariality=true）→ 收敛质量存疑，应提示")

    if len(effective) < 3:
        rp.w("7.4", f"有效表态仅 {len(effective)} 条，'高一致度'可能是过早共识而非真共识")

    # 保留事项 → 强制停在 S5
    reserved_items = sorted(set(reserved_items))
    if reserved_items:
        rp.i("存在保留事项 → 案件必须停在 S5_CONVERGED，禁止任何 agent 给出终局裁定（§10.1）")

    if cold_count < COLD_RELEASE_THRESHOLD:
        rp.i(f"冷方 {cold_count}/{COLD_RELEASE_THRESHOLD} → 即使裁定完成也不得进入 S7_PUBLISHED（§9.2）")

    next_state = "S5_CONVERGED" if not blocking else (
        "S8_SUSPENDED" if not valid_challenges else "S2_ROUND")

    return {
        "weighted_agreement": agreement,
        "leading_verdict": top_verdict,
        "threshold": theta,
        "participants": participants,
        "effective_positions": len(effective),
        "abstained": abstain,
        "cold_count": cold_count,
        "byzantine_tolerance_f": f_tol,
        "role_coverage": roles_present,
        "challenges_raised": len(valid_challenges),
        "challenges_resolved": len(rebuttals),
        "low_adversariality": low_adv,
        "blocking_objections": blocking,
        "degraded_mode": participants < MIN_PARTICIPANTS_BFT,
        "next_state": next_state,
        "reserved_for_adjudication": reserved_items,
        "_weights": effective,
    }


# ---------------------------------------------------------------- 主流程

def run(path, fill=False, as_json=False):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[错误] 无法读取/解析 {path}: {e}")
        return 2

    messages = doc.get("messages") or []
    ledger_sha = doc.get("ledger_sha256", "")
    if not messages:
        print("[错误] 文件中没有 messages 数组")
        return 2

    if fill:
        fill_chain(messages)

    rp = Report()

    # 逐条校验
    for m in messages:
        check_envelope(m, ledger_sha, rp)
        t = m.get("msg_type")
        if t == "POSITION":
            check_position(m, rp)
        elif t == "CHALLENGE":
            check_challenge(m, rp)
        elif t == "REBUTTAL":
            check_rebuttal(m, rp)

    # 哈希链连续性
    prev = None
    for m in messages:
        if m.get("hash") and m.get("prev_hash", "__miss__") != "__miss__":
            if m["prev_hash"] != prev:
                rp.v("HASH", f"[{m['msg_id']}] prev_hash 断链（§11.3）")
            prev = m["hash"]

    call = next((m for m in messages if m["msg_type"] == "CALL"), None)
    theta = (call or {}).get("payload", {}).get("theta", DEFAULT_THETA)

    # §10.4 责任链四栏
    if call:
        rc = call["payload"].get("responsibility_chain") or {}
        for f in ("recorder", "verifiers", "adjudicator", "bearer"):
            if not rc.get(f):
                rp.v("10.4", f"CALL 责任链缺 {f} → 无责任链的案件不得进入验证")

    conv = compute_convergence(messages, theta, rp)

    # 任何 MUST 违规都不得给出"可推进"的状态建议：先修正，再重新提交
    if rp.violations:
        conv["next_state"] = "BLOCKED_PENDING_FIX"

    # 若文件里已有 CONVERGENCE_REPORT，比对是否与重算结果一致
    existing = next((m for m in messages if m["msg_type"] == "CONVERGENCE_REPORT"), None)
    if existing:
        ep = existing["payload"]
        for k in ("weighted_agreement", "participants", "cold_count", "next_state"):
            if k in ep and ep[k] != conv[k]:
                if fill:
                    ep[k] = conv[k]
                else:
                    rp.w("ORC", f"收敛报告 {k}={ep[k]} 与重算值 {conv[k]} 不一致")
        if fill:
            ep["byzantine_tolerance_f"] = conv["byzantine_tolerance_f"]
            ep["role_coverage"] = conv["role_coverage"]
            ep["challenges_raised"] = conv["challenges_raised"]
            ep["low_adversariality"] = conv["low_adversariality"]
            ep["blocking_objections"] = conv["blocking_objections"]
            ep["degraded_mode"] = conv["degraded_mode"]
            ep["threshold"] = conv["threshold"]
            # 重算后哈希失效，重填链
            fill_chain(messages)

    if fill:
        Path(path).write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    result = {
        "file": str(path),
        "case_id": doc.get("case_id"),
        "messages": len(messages),
        "convergence": {k: v for k, v in conv.items() if k != "_weights"},
        "weights": conv["_weights"],
        "violations": rp.violations,
        "warnings": rp.warnings,
        "info": rp.info,
        "verdict": "PASS" if rp.ok else "BLOCKED",
    }

    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if rp.ok else 1

    # 人类可读输出
    print("=" * 68)
    print(f"SXJ-MAIP/{MAIP_VERSION} 校验报告   案件：{doc.get('case_id')}   消息数：{len(messages)}")
    print("=" * 68)
    if fill:
        print("✔ 已回填哈希链并重算收敛报告\n")

    print("【权重明细】（w = base×conf×trust；冷方 base=1.0，热方 0.5）")
    for e in conv["_weights"]:
        print(f"  {e['agent']:<22} {e['role']:<9} {e['tier']:<5} "
              f"{e['verdict']:<12} conf={e['confidence']:<5} w={e['weight']}")
    for a in conv["abstained"]:
        print(f"  {a['agent']:<22} {'—':<9} {'—':<5} {str(a['verdict']):<12} abstain（{a['reason']}）")

    print(f"\n【收敛】主流结论={conv['leading_verdict']}  加权一致度={conv['weighted_agreement']}"
          f"（阈值 {conv['threshold']}）")
    print(f"【容错】参与方={conv['participants']}  可容错 f={conv['byzantine_tolerance_f']}  "
          f"冷方={conv['cold_count']}/{COLD_RELEASE_THRESHOLD}")
    print(f"【角色】{conv['role_coverage']}")
    print(f"【质疑】有效质疑={conv['challenges_raised']}  答辩={conv['challenges_resolved']}  "
          f"仅轮值方质疑={conv['low_adversariality']}")

    if rp.violations:
        print(f"\n❌ MUST 违规 {len(rp.violations)} 条（阻断）：")
        for v in rp.violations:
            print(f"  [{v['code']}] {v['msg']}")
    else:
        print("\n✅ 无 MUST 违规")

    if rp.warnings:
        print(f"\n⚠ 提示 {len(rp.warnings)} 条：")
        for w in rp.warnings:
            print(f"  [{w['code']}] {w['msg']}")

    if rp.info:
        print("\nℹ 状态说明：")
        for m in rp.info:
            print(f"  · {m}")

    if conv["reserved_for_adjudication"]:
        print("\n🔒 待决定层（人类）裁定的保留事项：")
        for r in conv["reserved_for_adjudication"]:
            print(f"  · {r}")

    print(f"\n→ 建议下一状态：{conv['next_state']}")
    print("=" * 68)
    return 0 if rp.ok else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    target = args[0]
    sys.exit(run(target, fill="--fill" in args, as_json="--json" in args))
