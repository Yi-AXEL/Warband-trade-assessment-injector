#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rare Item Scout Injector.

Purpose:
    Injects rare-item scouting logic into compiled menus without the Module System compiler.
    See Note/AI_note/rare_item_scout_notes.md for usage, constraints, and pitfalls.
"""

import sys
import os
import shutil
import argparse
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Set


# ============================================================
# 0. 诊断模式基础设定
# ============================================================

DIAG = False

def diag(*args, **kwargs):
    if DIAG:
        print("  [DIAG]", *args, **kwargs)


# ============================================================
# 1. Warband 编译常量
# ============================================================

OP_NUM_VALUE_BITS = 56
LOCAL_INDEX_MASK = (1 << OP_NUM_VALUE_BITS) - 1

TAG_REGISTER       = 1
TAG_VARIABLE       = 2
TAG_ITEM           = 4
TAG_TROOP          = 5
TAG_PARTY          = 9
TAG_MENU           = 12
TAG_LOCAL_VARIABLE = 17
TAG_SKILL          = 19
TAG_QUICK_STRING   = 22

OM_REG = TAG_REGISTER << OP_NUM_VALUE_BITS
OM_VAR = TAG_VARIABLE << OP_NUM_VALUE_BITS
OM_ITM = TAG_ITEM << OP_NUM_VALUE_BITS
OM_TRP = TAG_TROOP << OP_NUM_VALUE_BITS
OM_PRT = TAG_PARTY << OP_NUM_VALUE_BITS
OM_MNU = TAG_MENU << OP_NUM_VALUE_BITS
OM_LOC = TAG_LOCAL_VARIABLE << OP_NUM_VALUE_BITS
OM_SKL = TAG_SKILL << OP_NUM_VALUE_BITS
OM_QST = TAG_QUICK_STRING << OP_NUM_VALUE_BITS

P_MAIN  = OM_PRT | 0
TRP_PLY = OM_TRP | 0

SLOT_WEAPONSMITH = 21
SLOT_ARMORER     = 22
SLOT_MERCHANT    = 23
SLOT_HORSE_MERCH = 24
NUM_EQ_KINDS     = 10
MAX_INV_ITEMS    = 96

SCAN_THRESH  = 3
PREF_THRESH  = 6

LOCAL_BASE = 0

INJECT_SIG = 0x52617265
INJECT_START_SIG = 0x496E6A01
SIG_OPCODE = 2120


# ============================================================
# 2. 编码器
# ============================================================

class E:
    @staticmethod
    def L(n: int, base: int = LOCAL_BASE) -> int:
        return OM_LOC | (base + n)

    @staticmethod
    def R(n: int) -> int:
        return OM_REG | n

    @staticmethod
    def I(n: int) -> int:
        return OM_ITM | n

    @staticmethod
    def P(n: int) -> int:
        return OM_PRT | n

    @staticmethod
    def S(n: int) -> int:
        return OM_SKL | n

    @staticmethod
    def M(n: int) -> int:
        return OM_MNU | n

    @staticmethod
    def Q(n: int) -> int:
        return OM_QST | n

    try_begin   = staticmethod(lambda:    Operation(4, []))
    try_end     = staticmethod(lambda:    Operation(3, []))
    else_try    = staticmethod(lambda:    Operation(5, []))
    for_parties = staticmethod(lambda d:  Operation(11, [d]))
    for_range   = staticmethod(lambda d, l, u: Operation(6, [d, l, u]))

    assign    = staticmethod(lambda d, v: Operation(2133, [d, v]))
    val_add   = staticmethod(lambda d, v: Operation(2105, [d, v]))
    val_sub   = staticmethod(lambda d, v: Operation(2106, [d, v]))
    val_mul   = staticmethod(lambda d, v: Operation(2107, [d, v]))
    val_div   = staticmethod(lambda d, v: Operation(2108, [d, v]))
    val_min   = staticmethod(lambda d, v: Operation(2110, [d, v]))
    val_max   = staticmethod(lambda d, v: Operation(2111, [d, v]))
    store_sub = staticmethod(lambda d, a, b: Operation(2121, [d, a, b]))
    store_add = staticmethod(lambda d, a, b: Operation(2120, [d, a, b]))
    store_mul = staticmethod(lambda d, a, b: Operation(2122, [d, a, b]))

    sig_mark = staticmethod(
        lambda: Operation(SIG_OPCODE, [OM_LOC | 0, OM_LOC | 0, INJECT_SIG]))

    sig_start = staticmethod(
        lambda: Operation(SIG_OPCODE, [OM_LOC | 0, OM_LOC | 0, INJECT_START_SIG]))

    eq  = staticmethod(lambda a, b: Operation(31, [a, b]))
    ge  = staticmethod(lambda a, b: Operation(30, [a, b]))
    gt  = staticmethod(lambda a, b: Operation(32, [a, b]))
    lt  = staticmethod(lambda a, b: Operation(0x80000000 | 30, [a, b]))  # neg|ge
    le  = staticmethod(lambda a, b: Operation(0x80000000 | 32, [a, b]))  # neg|gt
    neq = staticmethod(lambda a, b: Operation(0x80000000 | 31, [a, b]))  # neg|eq

    slot_ge     = staticmethod(lambda p, s, v: Operation(561, [p, s, v]))
    get_slot    = staticmethod(lambda d, p, s: Operation(521, [d, p, s]))
    party_skill = staticmethod(lambda d, p, sk: Operation(1685, [d, p, sk]))
    is_hero     = staticmethod(lambda t: Operation(1507, [t]))
    is_wounded  = staticmethod(lambda t: Operation(1508, [t]))

    inv_slot    = staticmethod(lambda d, t, s: Operation(1541, [d, t, s]))
    inv_mod     = staticmethod(lambda d, t, s: Operation(1542, [d, t, s]))
    skl_level   = staticmethod(lambda d, sk, t: Operation(2170, [d, sk, t]))
    num_stacks  = staticmethod(lambda d, p: Operation(1650, [d, p]))
    stack_troop = staticmethod(lambda d, p, s: Operation(1652, [d, p, s]))

    str_clr   = staticmethod(lambda sr: Operation(2319, [sr]))
    str_set   = staticmethod(lambda sr, q: Operation(2320, [sr, q]))
    str_item  = staticmethod(lambda sr, i: Operation(2325, [sr, i]))
    str_party = staticmethod(lambda sr, p: Operation(2330, [sr, p]))
    str_troop = staticmethod(lambda sr, t: Operation(2322, [sr, t]))
    str_copy  = staticmethod(lambda d, s: Operation(2321, [d, s]))

#   `c` is the variable for the color of the messages in Recent Messages.
    msg = staticmethod(lambda sr, c=0x000000: Operation(1106, [sr, c]))
    jm  = staticmethod(lambda m: Operation(2060, [m]))

    @staticmethod
    def neg(op: Operation) -> Operation:
        result = Operation(op.opcode, list(op.args))
        result.opcode |= 0x80000000
        return result


# ============================================================
# 3. menus.txt 解析器（二进制模式 — forward-peek 策略）
# ============================================================

@dataclass
class Operation:
    opcode: int
    args: List[int]


@dataclass
class MenuOption:
    raw_id: str = ""
    conds: List[Operation] = field(default_factory=list)
    text: bytes = b""
    cons: List[Operation] = field(default_factory=list)


@dataclass
class Menu:
    raw_id: str = ""
    flags: int = 0
    text: bytes = b""
    mesh: bytes = b"none"
    ops: List[Operation] = field(default_factory=list)
    opts: List[MenuOption] = field(default_factory=list)


def read_file_bytes(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def read_file_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def write_file(path: str, content: bytes) -> None:
    with open(path, "wb") as f:
        f.write(content)


def _is_int_token(token: bytes) -> bool:
    try:
        int(token)
        return True
    except ValueError:
        return False


def _peek_menu_text_and_mesh(tokens: List[bytes], idx: int, tokens_len: int):
    """向前窥视解析菜单文本（m.text）和 mesh 名称。

    利用「非整数 token + 后两个整数 token」的模式识别 mesh 边界。
    <mesh> 是非整数字符串（如 "none"），其后紧接 ops_cnt（整数）和 opcode（整数）。

    返回 (text_bytes, mesh_bytes, new_idx)。
    """
    parts: List[bytes] = []
    while idx < tokens_len:
        if _is_int_token(tokens[idx]):
            parts.append(tokens[idx])
            idx += 1
        else:
            candidate = tokens[idx]
            if (idx + 2 < tokens_len
                and _is_int_token(tokens[idx + 1])
                and _is_int_token(tokens[idx + 2])):
                return b" ".join(parts), candidate, idx + 1
            parts.append(candidate)
            idx += 1
    raise ValueError(f"菜单文本解析失败：token 不足 (idx={idx}, total={tokens_len})")


def _peek_opt_text(tokens: List[bytes], idx: int, bound: int):
    """在 bound 限制内，向前窥视解析选项文本和 cons_cnt。

    识别 cons_cnt 边界的方法：
      (a) 三个连续整数 → cons_cnt + opcode + arg_count
      (b) 整数 + "." → cons_cnt + 选项终止符
      (c) 整数 + "mno_" → cons_cnt + 下一个选项 ID

    返回 (text_bytes, cons_cnt_int, new_idx)。
    """
    parts: List[bytes] = []
    if idx >= bound:
        return b"", 0, idx
    while idx < bound:
        if _is_int_token(tokens[idx]):
            cnt = int(tokens[idx])
            if (idx + 2 < bound
                and _is_int_token(tokens[idx + 1])
                and _is_int_token(tokens[idx + 2])):
                return b" ".join(parts), cnt, idx + 1
            if idx + 1 <= bound and idx + 1 < len(tokens) and tokens[idx + 1] == b".":
                return b" ".join(parts), cnt, idx + 1
            if idx + 1 <= bound and idx + 1 < len(tokens) and tokens[idx + 1].startswith(b"mno_"):
                return b" ".join(parts), cnt, idx + 1
        parts.append(tokens[idx])
        idx += 1
    raise ValueError(f"选项文本解析失败：idx={idx} 到达 bound={bound} 仍未找到 cons_cnt")


def _find_opt_boundary(tokens: List[bytes], idx: int, tokens_len: int) -> int:
    """找到当前选项的边界：下一个 "."（终止符）或 "mno_"（下个选项）的位置。
    返回 bound index（不包含 bound 本身）。如果can't find，返回 tokens_len。
    """
    for j in range(idx, tokens_len):
        if tokens[j] == b".":
            return j
        if tokens[j].startswith(b"mno_"):
            return j
    return tokens_len


def parse_menu_bytes(filepath: str) -> List[Menu]:
    raw = read_file_bytes(filepath)
    tokens = raw.split()
    idx = 0
    tokens_len = len(tokens)

    if idx >= tokens_len or tokens[idx] != b"menusfile":
        print("错误：文件头缺失（期望以 'menusfile' 开头）")
        sys.exit(1)
    idx += 3

    if idx >= tokens_len:
        print("错误：文件格式错误，无法读取菜单总数")
        sys.exit(1)
    count = int(tokens[idx])
    idx += 1
    menus: List[Menu] = []

    for menu_idx in range(count):
        if idx >= tokens_len:
            print(f"错误：文件格式错误，在第 {menu_idx + 1} 个菜单附近 token 不足")
            sys.exit(1)

        m = Menu()
        m.raw_id = tokens[idx].decode("ascii"); idx += 1
        m.flags = int(tokens[idx]); idx += 1
        m.text, m.mesh, idx = _peek_menu_text_and_mesh(tokens, idx, tokens_len)

        if idx >= tokens_len:
            print(f"错误：文件格式错误，菜单 {m.raw_id} 的操作计数缺失")
            sys.exit(1)
        ops_cnt = int(tokens[idx]); idx += 1
        for _ in range(ops_cnt):
            if idx + 1 >= tokens_len:
                print(f"错误：文件格式错误，菜单 {m.raw_id} 的操作 token 不足")
                sys.exit(1)
            code = int(tokens[idx])
            nargs = int(tokens[idx + 1])
            if idx + 2 + nargs > tokens_len:
                print(f"错误：文件格式错误，菜单 {m.raw_id} 的操作参数不足")
                sys.exit(1)
            args = [int(t) for t in tokens[idx + 2: idx + 2 + nargs]]
            m.ops.append(Operation(code, args))
            idx += 2 + nargs

        if idx >= tokens_len:
            print(f"错误：文件格式错误，菜单 {m.raw_id} 的选项计数缺失")
            sys.exit(1)
        opt_cnt = int(tokens[idx]); idx += 1
        for _ in range(opt_cnt):
            if idx >= tokens_len:
                print(f"错误：文件格式错误，菜单 {m.raw_id} 的选项 token 不足")
                sys.exit(1)
            o = MenuOption(raw_id=tokens[idx].decode("ascii")); idx += 1

            cond_cnt = int(tokens[idx]); idx += 1
            for _ in range(cond_cnt):
                if idx + 1 >= tokens_len:
                    print(f"错误：文件格式错误，选项 {o.raw_id} 的条件 token 不足")
                    sys.exit(1)
                code = int(tokens[idx])
                nargs = int(tokens[idx + 1])
                if idx + 2 + nargs > tokens_len:
                    print(f"错误：文件格式错误，选项 {o.raw_id} 的条件参数不足")
                    sys.exit(1)
                args = [int(t) for t in tokens[idx + 2: idx + 2 + nargs]]
                o.conds.append(Operation(code, args))
                idx += 2 + nargs

            # 先确定选项边界（最近的 "." 或 "mno_"），防止 _peek_opt_text 越界
            opt_bound = _find_opt_boundary(tokens, idx, tokens_len)
            o.text, cons_cnt, idx = _peek_opt_text(tokens, idx, opt_bound)

            for _ in range(cons_cnt):
                if idx + 1 >= tokens_len:
                    print(f"错误：文件格式错误，选项 {o.raw_id} 的后果 token 不足")
                    sys.exit(1)
                code = int(tokens[idx])
                nargs = int(tokens[idx + 1])
                if idx + 2 + nargs > tokens_len:
                    print(f"错误：文件格式错误，选项 {o.raw_id} 的后果参数不足")
                    sys.exit(1)
                args = [int(t) for t in tokens[idx + 2: idx + 2 + nargs]]
                o.cons.append(Operation(code, args))
                idx += 2 + nargs

            # 跳过 cons ops 之后所有多余的文本 token（如 Door_to_the_town_center.），
            # 直到遇到 "."（选项终止符）、"mno_"（下一选项）、或 "menu_"（下一菜单）。
            # Warband 的 process_game_menus.py 在某些场景下（如 menuzendar 的门传送菜单）
            # 在 cons ops 末尾输出额外的文本字段，不计算在 nargs 中。
            while idx < tokens_len:
                t = tokens[idx]
                if t == b"." or t.startswith(b"mno_") or t.startswith(b"menu_"):
                    if t == b".":
                        idx += 1  # 跳过 "." 终止符
                    break
                idx += 1  # 跳过多余的文本 token（不消耗 mno_ 或 menu_）
            m.opts.append(o)
        menus.append(m)

    return menus


def serialize_menu_list(menus: List[Menu]) -> bytes:
    lines: List[bytes] = [b"menusfile version 1", str(len(menus)).encode("ascii")]
    for m in menus:
        parts: List[bytes] = [
            m.raw_id.encode("ascii"),
            str(m.flags).encode("ascii"),
            m.text,
            m.mesh,
            str(len(m.ops)).encode("ascii"),
        ]
        for op in m.ops:
            op_parts = [str(op.opcode).encode("ascii"), str(len(op.args)).encode("ascii")]
            op_parts.extend(str(a).encode("ascii") for a in op.args)
            parts.append(b" ".join(op_parts))
        parts.append(str(len(m.opts)).encode("ascii"))
        for o in m.opts:
            parts.append(o.raw_id.encode("ascii"))
            parts.append(str(len(o.conds)).encode("ascii"))
            for op in o.conds:
                op_parts = [str(op.opcode).encode("ascii"), str(len(op.args)).encode("ascii")]
                op_parts.extend(str(a).encode("ascii") for a in op.args)
                parts.append(b" ".join(op_parts))
            parts.append(o.text)
            parts.append(str(len(o.cons)).encode("ascii"))
            for op in o.cons:
                op_parts = [str(op.opcode).encode("ascii"), str(len(op.args)).encode("ascii")]
                op_parts.extend(str(a).encode("ascii") for a in op.args)
                parts.append(b" ".join(op_parts))
            parts.append(b".")
        lines.append(b" ".join(parts))
    return b"\n".join(lines) + b"\n"


# ============================================================
# 4. quick_strings.txt 管理器（二进制模式）
# ============================================================

class QStrManager:
    def __init__(self, filepath: str):
        self.path = filepath
        self.keys: List[str] = []
        self.vals: dict = {}
        self.lines: List[bytes] = []
        self._load()

    def _load(self) -> None:
        raw = read_file_bytes(self.path)
        self.lines = raw.split(b"\n")
        cnt = int(self.lines[0].strip())
        self.keys = []
        self.vals = {}
        for i in range(1, cnt + 1):
            if i >= len(self.lines):
                break
            line = self.lines[i].strip()
            if not line:
                continue
            sp = line.split(b" ", 1)
            if len(sp) >= 2:
                k = sp[0].decode("utf-8", errors="replace")
                v = sp[1].decode("utf-8", errors="replace")
                self.keys.append(k)
                self.vals[k] = v

    def add(self, qstr_text: str) -> Tuple[int, int]:
        # 将空格替换为下划线，匹配 module system 编译器的 replace_spaces 行为
        stored = qstr_text.replace(" ", "_")
        vals_list = [self.vals[k] for k in self.keys]
        for idx, (k, v) in enumerate(zip(self.keys, vals_list)):
            if v == stored:
                compiled = OM_QST | idx
                return idx, compiled

        base = "qstr_rare_"
        idx = 0
        while True:
            key = base + str(idx) if idx > 0 else base.rstrip("_")
            if key not in self.vals:
                break
            idx += 1
        self.keys.append(key)
        self.vals[key] = stored
        ins = len(self.lines) - 1
        self.lines.insert(ins, f"{key} {stored}".encode("utf-8"))
        self.lines[0] = str(len(self.keys)).encode("ascii")
        index = len(self.keys) - 1
        compiled = OM_QST | index
        return index, compiled

    def save(self) -> None:
        write_file(self.path, b"\n".join(self.lines))


# ============================================================
# 5. 扫描代码生成器 - 前缀列表 - 暂未考虑到模组添加额外前缀的情况
# ============================================================

IMOD_PREFIXES = [
    (1, "Cracked"), (2, "Rusty"), (3, "Bent"),
    (4, "Chipped"), (5, "Battered"), (6, "Poor"),
    (7, "Crude"), (8, "Old"), (9, "Cheap"),
    (10, "Fine"), (11, "Well Made"), (12, "Sharp"),
    (13, "Balanced"), (14, "Tempered"), (15, "Deadly"),
    (16, "Exquisite"), (17, "Masterwork"), (18, "Heavy"),
    (19, "Strong"), (20, "Powerful"), (21, "Tattered"),
    (22, "Ragged"), (23, "Rough"), (24, "Sturdy"),
    (25, "Thick"), (26, "Hardened"), (27, "Reinforced"),
    (28, "Superb"), (29, "Lordly"), (30, "Lame"),
    (31, "Swaybacked"), (32, "Stubborn"), (33, "Timid"),
    (34, "Meek"), (35, "Spirited"), (36, "Champion"),
    (37, "Fresh"), (38, "Day Old"), (39, "Two Days Old"),
    (40, "Smelling"), (41, "Rotten"), (42, "Large Bag of"),
]


IMOD_PREFIXES_ZH_CN = [
    (1, "开 裂 的"), (2, "生 锈 的"), (3, "弯 曲 的"),
    (4, "缺 口 的"), (5, "磨 损 的"), (6, "劣 质 的"),
    (7, "粗 糙 的"), (8, "旧"), (9, "便 宜 的"),
    (10, "优 质 的"), (11, "精 良 的"), (12, "锋 利 的"),
    (13, "平 衡 的"), (14, "回 火 的"), (15, "致 命 的"),
    (16, "精 致"), (17, "极 品"), (18, "重"),
    (19, "坚 硬 的"), (20, "有 力 的"), (21, "破 烂 的"),
    (22, "破 旧 的"), (23, "粗 糙 的"), (24, "结 实 的"),
    (25, "厚"), (26, "加 硬"), (27, "加 强"),
    (28, "华 丽"), (29, "豪 华"), (30, "瘸 腿"),
    (31, "背 伤"), (32, "倔 强 的"), (33, "胆 小 的"),
    (34, "温 顺 的"), (35, "活 泼 的"), (36, "一 流"),
    (37, "新 鲜"), (38, "隔 夜 的"), (39, "隔 两 夜 的"),
    (40, "臭"), (41, "烂"), (42, "一 大 袋"),
]




# ============================================================
# 5a. 文本辞典（支持多语言，目前暂时只支持英语和简体中文）
# ============================================================

TEXTS_EN = {
    "q_low": "@{s2}^---^You lack the trade expertise to scout for rare equipment. "
             "A trader with skill 3 or higher could collect information about where to find "
             "{s5}, {s6}, {s7}, and {s8} across the world.",
    "qitem": "@{s2}^{s6} in {s5}",
    "qh": "@{s2}^---^I also managed to spot some rare equipment on the market:",
    "qh2": "@{s2}^---^A trader with skill 6 or higher could also collect information "
           "of the quality of these wares.",
    "qn": "@{s2}^---^I found that {s5}, {s6}, {s7}, and {s8} are all absent in the markets.",
    "hint_low": "@You recall rumors that a trader skilled enough could use the "
                "assessment to scout for rare items across the world.",
    "hint_mid": "@You recall rumors that with even more trading expertise one "
                "could collect intelligence of the quality of rare items of rare items in addition to their location.",
    "hint_high": "@With your keen trading eye, you may also collect intelligence of "
                 "rare items and their quality across the world.",
}

TEXTS_ZH_CN = {
    "q_low": "@{s2}^---^没 有 足 够 的 交 易 技 能 来 打 探 稀 有 装 备 。"
             "队 伍 的 交 易 技 能 达 到 3 级 或 以 上 才 可 以 在 市 场 打 探 到 "
             "{s5} 、 {s6} 、 {s7} 和 {s8} 在 哪 里 有 卖 。",
    "qitem": "@{s2}^{s6}在 {s5}",
    "qh": "@{s2}^---^打 探 到 了 各 地 市 场 中 的 一 些 物 品 ：",
    "qh2": "@{s2}^---^队 伍 的 交 易 技 能 达 到 6 级 或 以 上 就 可 以 额 外 打 探 到 这 些 物 品 的 品 质 。",
    "qn": "@{s2}^---^我 在 市 场 中 没 有 发 现 {s5} 、 {s6} 、 {s7} 或 {s8} 在 出 售 。",
    "hint_low": "@你 回 想 起 一 些 传 闻 ， 一 个 有 足 够 交 易 技 能 的 人 可 以 "
                "借 助 行 情 评 估 来 打 探 稀 有 装 备 的 踪 迹 。",
    "hint_mid": "@你 回 想 起 一 些 传 闻 ， 有 更 高 交 易 技 能 的 话 甚 至 可 以 "
                "打 探 到 市 场 中 稀 有 物 品 的 品 质 。",
    "hint_high": "@凭 借 你 敏 锐 的 交 易 眼 光 ， 你 可 以 在 市 场 中 同 时 发 现 "
                 "稀 有 物 品 及 其 品 质 。",
}


def make_scan_ops(skill_ref: int, item1: int, item2: int, item3: int, item4: int,
                  qstr_mgr: QStrManager,
                  local_base: int = LOCAL_BASE,
                  lang: str = "en",
                  with_diag: bool = False) -> List[Operation]:
    ops: List[Operation] = []

    def L(n: int) -> int:
        return E.L(n, base=local_base)

    R = E.R

    def add_qstr(text: str) -> int:
        clean = text[1:] if text.startswith("@") else text
        _, val = qstr_mgr.add(clean)
        return val

    # Select text dictionary by language (D7)
    TEXTS = TEXTS_ZH_CN if lang == "zh-CN" else TEXTS_EN
    # Select IMOD prefix table by language (D12)
    IMOD_LIST = IMOD_PREFIXES_ZH_CN if lang == "zh-CN" else IMOD_PREFIXES

    # --- 开始标记块 ---
    ops += [E.assign(L(13), 0)]
    ops += [E.try_begin()]
    ops += [E.gt(L(13), 0)]
    ops += [E.sig_start()]
    ops += [E.sig_start()]
    ops += [E.try_end()]

    # --- Part 1: Get party trade skill ---
    ops += [E.party_skill(L(0), P_MAIN, skill_ref)]

    # --- Part 2: Skill gate ---
    ops += [E.try_begin()]
    ops += [E.lt(L(0), SCAN_THRESH)]
    # Low-skill branch
    if with_diag:
        ops += [E.assign(R(0), L(0))]
        q_low_mark = add_qstr("@[RARE] LOW_SKILL: L0={reg0}")
        ops += [E.str_set(0, q_low_mark)]
        ops += [E.msg(0)]

    # Store item names for {s5}{s6}{s7}{s8} macros (s5-s8 are free here)
    ops += [E.str_item(5, item1)]
    ops += [E.str_item(6, item2)]
    ops += [E.str_item(7, item3)]
    ops += [E.str_item(8, item4)]
    q_low = add_qstr(TEXTS["q_low"])
    ops += [E.str_set(2, q_low)]

    ops += [E.else_try()]
    ops += [E.ge(L(0), SCAN_THRESH)]
    # Scan branch
    if with_diag:
        ops += [E.assign(R(0), L(0))]
        q_scan_mark = add_qstr("@[RARE] SCAN_BRANCH: L0={reg0}")
        ops += [E.str_set(0, q_scan_mark)]
        ops += [E.msg(0)]

    # show_prefix
    ops += [E.assign(L(6), 0)]
    ops += [E.try_begin()]
    ops += [E.ge(L(0), PREF_THRESH)]
    ops += [E.assign(L(6), 1)]
    ops += [E.try_end()]

    # Counter initialization
    ops += [E.assign(L(14), 0)]
    ops += [E.assign(L(15), 0)]
    ops += [E.assign(L(16), 0)]
    ops += [E.assign(L(17), 0)]
    ops += [E.assign(L(18), 0)]  # found_4

    # ★ Set header BEFORE scan — scan appends to it, overwrite avoided
    qh = add_qstr(TEXTS["qh"])
    ops += [E.str_set(2, qh)]

    # --- Part 3: Triple scan (appends to s2) ---
    item_entries = [(item1, L(15)), (item2, L(16)), (item3, L(17)), (item4, L(18))]

    qitem_fmt = TEXTS["qitem"]

    for slot_type in [SLOT_WEAPONSMITH, SLOT_ARMORER, SLOT_MERCHANT, SLOT_HORSE_MERCH]:
        ops += [E.for_parties(L(7))]
        ops += [E.slot_ge(L(7), slot_type, 1)]
        ops += [E.get_slot(L(8), L(7), slot_type)]
        ops += [E.assign(L(9), 0)]
        ops += [E.for_range(L(10), NUM_EQ_KINDS, MAX_INV_ITEMS + NUM_EQ_KINDS)]
        ops += [E.inv_slot(L(11), L(8), L(10))]

        # Early exit: empty slot (D10)
        ops += [E.try_begin()]
        ops += [E.lt(L(11), 0)]
        ops += [E.assign(L(10), 106)]
        ops += [E.try_end()]

        # [A] Not found in this town yet
        ops += [E.try_begin()]
        ops += [E.eq(L(9), 0)]

        for item_val, found_reg in item_entries:
            # [B] Item match
            ops += [E.try_begin()]
            ops += [E.eq(L(11), item_val)]
            ops += [E.val_add(found_reg, 1)]
            ops += [E.val_add(L(14), 1)]

            # [C] show_prefix with IMOD chain
            ops += [E.try_begin()]
            ops += [E.eq(L(6), 1)]
            ops += [E.inv_mod(L(12), L(8), L(10))]
            ops += [E.str_item(6, L(11))]
            for first, (imod, prefix) in enumerate(IMOD_LIST):
                if first == 0:
                    ops += [E.try_begin()]
                else:
                    ops += [E.else_try()]
                ops += [E.eq(L(12), imod)]
                qpre = add_qstr(f"@{prefix} {{s6}}")
                ops += [E.str_set(6, qpre)]
            ops += [E.try_end()]  # end IMOD chain
            ops += [E.str_party(5, L(7))]
            qline_with = add_qstr(qitem_fmt)
            ops += [E.str_set(2, qline_with)]
            ops += [E.else_try()]
            ops += [E.str_item(6, L(11))]
            ops += [E.str_party(5, L(7))]
            qline_without = add_qstr(qitem_fmt)
            ops += [E.str_set(2, qline_without)]
            ops += [E.try_end()]  # end [C]

            ops += [E.assign(L(9), 1)]  # found_in_town = 1
            ops += [E.try_end()]  # end [B]

        ops += [E.try_end()]  # [A] end
        ops += [E.try_end()]  # end for_range
        ops += [E.try_end()]  # end for_parties


    # --- Part 4: Post-scan branch (found-any guard) ---
    ops += [E.try_begin()]
    ops += [E.gt(L(14), 0)]
    if with_diag:
        q_found_mark = add_qstr("@[RARE] FOUND_BRANCH")
        ops += [E.str_set(0, q_found_mark)]
        ops += [E.msg(0)]

    # Quality hint
    ops += [E.try_begin()]
    ops += [E.lt(L(0), PREF_THRESH)]
    qh2 = add_qstr(TEXTS["qh2"])
    ops += [E.str_set(2, qh2)]
    ops += [E.try_end()]

    ops += [E.else_try()]
    if with_diag:
        q_absent_mark = add_qstr("@[RARE] ABSENT_BRANCH")
        ops += [E.str_set(0, q_absent_mark)]
        ops += [E.msg(0)]

    # Store item names for macros
    ops += [E.str_item(5, item1)]
    ops += [E.str_item(6, item2)]
    ops += [E.str_item(7, item3)]
    ops += [E.str_item(8, item4)]
    qn = add_qstr(TEXTS["qn"])
    ops += [E.str_set(2, qn)]

    ops += [E.try_end()]   # end found_any
    ops += [E.try_end()]   # end skill_gate

    # --- 结束标记块 ---
    ops += [E.assign(L(13), 0)]
    ops += [E.try_begin()]
    ops += [E.gt(L(13), 0)]
    ops += [E.sig_mark()]
    ops += [E.sig_mark()]
    ops += [E.try_end()]

    return ops



def make_begin_hint_ops(skill_ref: int,
                         qstr_mgr: QStrManager,
                         lang: str = "en",
                         with_diag: bool = False) -> List[Operation]:
    """生成 menu_town_trade_assessment_begin 的提示文本"""
    ops: List[Operation] = []
    TEXTS = TEXTS_ZH_CN if lang == "zh-CN" else TEXTS_EN

    def add_qstr(text: str) -> int:
        clean = text[1:] if text.startswith("@") else text
        _, val = qstr_mgr.add(clean)
        return val

    def L(n: int) -> int:
        return E.L(n, base=0)  # reuse local 0..5 like main inject (safe: begin menu ops are executed first)

    # Display hint via str_set(2) + msg(2) — diag markers prove msg() works in menu ops
    ops += [E.party_skill(L(0), P_MAIN, skill_ref)]

    # 三段式技能门控
    ops += [E.try_begin()]
    ops += [E.lt(L(0), SCAN_THRESH)]  # < 3
    q_low = add_qstr(TEXTS["hint_low"])
    ops += [E.str_set(2, q_low)]
    ops += [E.msg(2)]
    if with_diag:
        ops += [E.msg(0)]

    ops += [E.else_try()]
    ops += [E.ge(L(0), SCAN_THRESH)]  # >= 3
    ops += [E.try_begin()]
    ops += [E.lt(L(0), PREF_THRESH)]  # 3-5
    q_mid = add_qstr(TEXTS["hint_mid"])
    ops += [E.str_set(2, q_mid)]
    ops += [E.msg(2)]
    if with_diag:
        ops += [E.msg(0)]

    ops += [E.else_try()]
    ops += [E.ge(L(0), PREF_THRESH)]  # >= 6
    q_high = add_qstr(TEXTS["hint_high"])
    ops += [E.str_set(2, q_high)]
    ops += [E.msg(2)]
    if with_diag:
        ops += [E.msg(0)]
    ops += [E.try_end()]  # end mid/high

    ops += [E.try_end()]  # end low/else
    return ops



def summarize_ops(ops: List[Operation], label: str = "") -> None:
    """输出 ops 列表的结构摘要，不打印原始数字。"""
    diag(f"--- {label} 结构摘要 ---")

    # 块结构计数
    try_begin = sum(1 for op in ops if op.opcode == 4)
    try_end = sum(1 for op in ops if op.opcode == 3)
    else_try = sum(1 for op in ops if op.opcode == 5)
    for_range = sum(1 for op in ops if op.opcode == 6)
    for_parties = sum(1 for op in ops if op.opcode == 11)

    openers = try_begin + for_range + for_parties
    closers = try_end

    diag(f"  块: try_begin={try_begin}, else_try={else_try}, try_end={try_end}")
    diag(f"  循环: for_range={for_range}, for_parties={for_parties}")
    diag(f"  配对: openers={openers}, closers={closers}  {'✅' if openers == closers else '❌ 不平衡!'}")

    # str_set / display_message 计数
    str_sets = [op for op in ops if op.opcode == 2320]
    diag(f"  str_set 数量: {len(str_sets)}")
    for s in str_sets:
        reg = s.args[0]
        qstr_idx = s.args[1] & LOCAL_INDEX_MASK if (s.args[1] >> OP_NUM_VALUE_BITS) == TAG_QUICK_STRING else s.args[1]
        qstr_tag = s.args[1] >> OP_NUM_VALUE_BITS
        tag_name = {TAG_QUICK_STRING: "QST", TAG_REGISTER: "REG", TAG_LOCAL_VARIABLE: "LOC"}.get(qstr_tag, f"TAG{qstr_tag}")
        diag(f"    str_set(s{reg}, {tag_name}|{qstr_idx})")

    # 条件比较
    eqs = [op for op in ops if op.opcode in (31, 32, 30, 33, 34, 35)]
    diag(f"  条件操作: {len(eqs)}")
    opname_map = {31:"eq", 32:"lt", 30:"ge", 33:"gt", 34:"neq", 35:"le"}
    for e in eqs[:10]:  # 只打前 10 条
        oname = opname_map.get(e.opcode, f"op{e.opcode}")
        diag(f"    {oname}({e.args[0]}, {e.args[1]})")

    # 关键操作
    diag(f"  party_skill(1685): {sum(1 for op in ops if op.opcode == 1685)}")
    diag(f"  inv_slot(1541):   {sum(1 for op in ops if op.opcode == 1541)}")
    diag(f"  inv_mod(1542):    {sum(1 for op in ops if op.opcode == 1542)}")
    diag(f"  msg(1106):         {sum(1 for op in ops if op.opcode == 1106)}")


def dump_local_alloc(alloc_base: int) -> None:
    """输出局部变量分配表。"""
    allocs = [
        (0,  "max_skill"),
        (6,  "show_prefix"),
        (7,  "cur_town"),
        (8,  "merchant"),
        (9,  "found_in_town"),
        (10, "i_slot"),
        (11, "slot_item"),
        (12, "mod_val"),
        (13, "sig_guard"),
        (14, "found_any"),
        (15, "found_1"),
        (16, "found_2"),
        (17, "found_3"),
        (18, "found_4"),
    ]
    diag(f"局部变量基址: {alloc_base}")
    diag(f"使用范围: {alloc_base}..{alloc_base + 18}")
    for offset, name in allocs:
        diag(f"  L({offset}) = OM_LOC|{alloc_base + offset}  # :{name}")




# ============================================================
# 6. 辅助函数
# ============================================================


def extract_skl_trade(menus: List[Menu]) -> Optional[int]:
    """Extract the compiled skl_trade constant from menus.txt.

    Deterministic search: trade-assessment menus first (in fixed order),
    then all others.  Recognises store_skill_level (2170),
    party_get_skill_level (1685), and call_script (1) — whichever op
    first carries a SKL-tagged argument.
    """
    def _tag(val): return (val >> OP_NUM_VALUE_BITS) == TAG_SKILL
    def _scan(ops):
        for op in ops:
            if op.opcode == 2170 and len(op.args) >= 2 and _tag(op.args[1]):
                return op.args[1]
            if op.opcode == 1685 and len(op.args) >= 3 and _tag(op.args[2]):
                return op.args[2]
            if op.opcode == 1 and len(op.args) >= 2 and _tag(op.args[1]):
                return op.args[1]
        return None

    target_ids = ["menu_town_trade_assessment_begin",
                  "menu_town_trade_assessment"]
    for tid in target_ids:
        for m in menus:
            if m.raw_id == tid:
                r = _scan(m.ops)
                if r is not None:
                    return r
    for m in menus:
        if m.raw_id not in target_ids:
            r = _scan(m.ops)
            if r is not None:
                return r
    return None


def find_continue_option(menu: Menu) -> Optional[MenuOption]:
    for o in menu.opts:
        if o.raw_id == "mno_continue":
            return o
    if menu.opts:
        print("  # 未找到 mno_continue，使用最后一个选项")
        return menu.opts[-1]
    return None


def find_display_message_in_cons(cons: List[Operation]) -> tuple:
    has_any = False
    has_correct = False
    bad_indices: List[int] = []
    for i, op in enumerate(cons):
        if op.opcode == 1106:
            has_any = True
            if len(op.args) >= 1 and op.args[0] == 2:
                has_correct = True
            else:
                bad_indices.append(i)
    return has_any, has_correct, bad_indices


def fix_display_message(cont_opt: MenuOption) -> bool:
    has_any, has_correct, bad_indices = find_display_message_in_cons(cont_opt.cons)
    for idx in reversed(bad_indices):
        del cont_opt.cons[idx]
    if not has_correct:
        msg_op = E.msg(2)
        if cont_opt.cons:
            cont_opt.cons.insert(-1, msg_op)
        else:
            cont_opt.cons.append(msg_op)
        return True
    return False

# ============================================================
# 7. 注入幂等性 — 双标记检测/清除 + 启发式 fallback
# ============================================================


def _is_sig_start(op: Operation) -> bool:
    """检查 op 是否为开始签名 (store_add, [OM_LOC|0, OM_LOC|0, INJECT_START_SIG])。"""
    return (op.opcode == SIG_OPCODE and len(op.args) == 3
            and (op.args[0] & LOCAL_INDEX_MASK) == 0
            and (op.args[1] & LOCAL_INDEX_MASK) == 0
            and op.args[2] == INJECT_START_SIG)


def _is_sig_end(op: Operation) -> bool:
    """检查 op 是否为结束签名 (store_add, [OM_LOC|0, OM_LOC|0, INJECT_SIG])。"""
    return (op.opcode == SIG_OPCODE and len(op.args) == 3
            and (op.args[0] & LOCAL_INDEX_MASK) == 0
            and (op.args[1] & LOCAL_INDEX_MASK) == 0
            and op.args[2] == INJECT_SIG)


def _find_start_marker(ops: List[Operation]) -> Optional[int]:
    """从头部扫描，找到开始标记块的 assign 所在索引。"""
    for i in range(len(ops) - 5):
        if (ops[i].opcode == 2133 and len(ops[i].args) == 2 and ops[i].args[1] == 0
            and ops[i+1].opcode == 4
            and ops[i+2].opcode == 32
            and _is_sig_start(ops[i+3]) and _is_sig_start(ops[i+4])
            and ops[i+5].opcode == 3):
            return i
    return None


def _find_end_marker(ops: List[Operation]) -> Optional[int]:
    """从尾部反向扫描，找到结束标记块的 assign 所在索引。"""
    for i in range(len(ops) - 5, -1, -1):
        if (ops[i].opcode == 2133 and len(ops[i].args) == 2 and ops[i].args[1] == 0
            and ops[i+1].opcode == 4
            and ops[i+2].opcode == 32
            and _is_sig_end(ops[i+3]) and _is_sig_end(ops[i+4])
            and ops[i+5].opcode == 3):
            return i
    return None


def has_injection_signature(ops: List[Operation]) -> bool:
    """检测 ops 中是否同时存在开始和结束标记块。"""
    return (_find_start_marker(ops) is not None
            and _find_end_marker(ops) is not None)


def remove_old_injection(ops: List[Operation]) -> List[Operation]:
    """找到首尾双标记并删除整个注入块（含标记）。"""
    start_idx = _find_start_marker(ops)
    end_idx = _find_end_marker(ops)
    if start_idx is not None and end_idx is not None and start_idx < end_idx:
        # 删除从 start_idx 到 end_idx+5（最后一个标记块的 try_end）之间的所有 op
        return ops[:start_idx] + ops[end_idx + 6:]
    # 旧版本兼容：只有结束标记（裸 sig_mark 在尾部）
    if end_idx is not None:
        return ops[:end_idx] + ops[end_idx + 6:]
    # 旧版本兼容：只有尾部裸 sig_mark（无 assign/try_begin/gt 包裹）
    for i in range(len(ops) - 1, -1, -1):
        if _is_sig_end(ops[i]):
            return ops[:i]
    return ops


def heuristic_scan_report(ops: List[Operation]) -> dict:
    result = {
        "suspected": False,
        "feature_count": 0,
        "first_feature_idx": None,
        "details": "",
        "try_pairs": 0,
    }
    if len(ops) < 5:
        return result

    feature_start = None
    consecutive = 0
    try_begin_count = 0
    try_end_count = 0

    for i in range(len(ops) - 1, -1, -1):
        op = ops[i]
        is_feature = False

        if op.opcode == 11 and i + 1 < len(ops) and ops[i + 1].opcode == 561:
            is_feature = True
        if op.opcode == 2320 and len(op.args) >= 2:
            if (op.args[1] >> OP_NUM_VALUE_BITS) == TAG_QUICK_STRING:
                is_feature = True

        if op.opcode == 4:
            try_begin_count += 1
        if op.opcode == 3:
            try_end_count += 1

        if is_feature:
            consecutive += 1
            feature_start = i
        else:
            if op.opcode in (6, 4, 3, 5, 2133, 2105, 2325, 2330, 2322, 1507, 1508, 1541, 1542, 2170):
                consecutive += 1
                if feature_start is None:
                    feature_start = i
            else:
                break

    result["try_pairs"] = min(try_begin_count, try_end_count)
    HEUR_THRESH = 15

    if consecutive > HEUR_THRESH:
        result["suspected"] = True
        result["feature_count"] = consecutive
        result["first_feature_idx"] = feature_start
        result["details"] = (
            f"从 ops 尾部检测到 {consecutive} 条连续操作疑似旧注入代码"
            f"（try_begin/try_end 配对: {try_begin_count}/{try_end_count}）"
        )
    else:
        result["feature_count"] = consecutive
        if consecutive > 0:
            result["details"] = (
                f"尾部检测到 {consecutive} 条可疑操作（阈值 {HEUR_THRESH}），不足以触发自动清理"
            )
        else:
            result["details"] = "未检测到疑似旧注入代码"

    return result


def clean_old_injection(ops: List[Operation], force: bool = False,
                        dry_run: bool = False) -> tuple:
    """清理旧注入。
    
    签名检测自动清除。启发式需 --force。dry-run 不执行启发式清除。
    返回 (cleaned_ops, report)。
    """
    report = {
        "signature_found": False,
        "heuristic_found": False,
        "cleaned": False,
        "heuristic_details": "",
    }

    sig_found = has_injection_signature(ops)
    report["signature_found"] = sig_found

    if sig_found:
        cleaned = remove_old_injection(ops)
        report["cleaned"] = True
        return cleaned, report

    hr = heuristic_scan_report(ops)
    report["heuristic_details"] = hr["details"]

    if hr["suspected"]:
        if dry_run:
            # dry-run 模式：只报告，不执行
            report["heuristic_found"] = True
            report["cleaned"] = False
            return ops, report
        if not force:
            report["heuristic_found"] = True
            report["cleaned"] = False
            report["heuristic_details"] += (
                "  （需 --force 确认后方可清除）")
            return ops, report
        report["heuristic_found"] = True
        report["cleaned"] = True
        cleaned = ops[:hr["first_feature_idx"]]
        return cleaned, report

    return ops, report


# ============================================================
# 8. 验证函数
# ============================================================


def normalize_ws(b: bytes) -> bytes:
    """Warband ignores redundant whitespace; bytes.split() + b" ".join()
    collapses consecutive spaces. Normalize for comparison."""
    while b"  " in b:
        b = b.replace(b"  ", b" ")
    return b



def verify_roundtrip(filepath: str) -> List[str]:
    errors: List[str] = []
    menus1 = parse_menu_bytes(filepath)
    serialized = serialize_menu_list(menus1)

    import tempfile
    fd, tmp_path = tempfile.mkstemp(suffix=".roundtrip", prefix="warband_")
    os.close(fd)
    try:
        write_file(tmp_path, serialized)
        menus2 = parse_menu_bytes(tmp_path)

        if len(menus1) != len(menus2):
            errors.append(f"菜单数量不一致: {len(menus1)} vs {len(menus2)}")
            return errors

        for i, (m1, m2) in enumerate(zip(menus1, menus2)):
            if m1.raw_id != m2.raw_id:
                errors.append(f"菜单 {i} raw_id 不一致: {m1.raw_id} vs {m2.raw_id}")
            if m1.flags != m2.flags:
                errors.append(f"菜单 {m1.raw_id} flags 不一致")
            if m1.text != m2.text:
                errors.append(f"菜单 {m1.raw_id} text 不一致")
            if m1.mesh != m2.mesh:
                errors.append(f"菜单 {m1.raw_id} mesh 不一致")
            if len(m1.ops) != len(m2.ops):
                errors.append(f"菜单 {m1.raw_id} ops 数不一致")
            else:
                for j, (op1, op2) in enumerate(zip(m1.ops, m2.ops)):
                    if op1.opcode != op2.opcode or op1.args != op2.args:
                        err_msg = f"菜单 {m1.raw_id} op{j} 不一致"
                        if DIAG:
                            err_msg += f"\n    [DIAG] 解析:   opcode={op1.opcode}, args={op1.args}"
                            err_msg += f"\n    [DIAG] 序列化后: opcode={op2.opcode}, args={op2.args}"
                        errors.append(err_msg)
            if len(m1.opts) != len(m2.opts):
                errors.append(f"菜单 {m1.raw_id} opts 数不一致")
            else:
                for j, (o1, o2) in enumerate(zip(m1.opts, m2.opts)):
                    if o1.raw_id != o2.raw_id or o1.text != o2.text:
                        errors.append(f"菜单 {m1.raw_id} opt{j} 属性不一致")
                    if len(o1.conds) != len(o2.conds):
                        errors.append(f"opt {o1.raw_id} conds 数不一致")
                    if len(o1.cons) != len(o2.cons):
                        errors.append(f"opt {o1.raw_id} cons 数不一致")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return errors


def post_inject_verify(menus_path: str) -> None:
    """写入文件后重新解析验证。"""
    if not DIAG:
        return
    try:
        menus2 = parse_menu_bytes(menus_path)
    except Exception as e:
        diag(f"post_inject_verify: 重新解析失败: {e}")
        return

    try:
        target2 = next(m for m in menus2 if m.raw_id == "menu_town_trade_assessment")
    except StopIteration:
        diag("post_inject_verify: can't find menu_town_trade_assessment")
        return

    diag(f"--- 写入文件后验证 ---")

    # 检查注入签名
    sig_found = has_injection_signature(target2.ops)
    diag(f"文件中签名检测: {'✅' if sig_found else '❌ 缺失'}")

    # 检查块配对
    tb = sum(1 for op in target2.ops if op.opcode == 4)
    te = sum(1 for op in target2.ops if op.opcode == 3)
    fr = sum(1 for op in target2.ops if op.opcode == 6)
    fp = sum(1 for op in target2.ops if op.opcode == 11)
    openers = tb + fr + fp
    diag(f"文件中块配对: try_begin={tb}, for_range={fr}, for_parties={fp}")
    diag(f"  openers={openers}, closers={te}  {'✅' if openers == te else '❌ 不平衡'}")

    # 定位所有 party_get_skill_level 操作
    for i, op in enumerate(target2.ops):
        if op.opcode == 1685:
            diag(f"发现 party_get_skill_level 在 ops[{i}]")
            diag(f"  参数: [{op.args[0]}, {op.args[1]}, {op.args[2]}]")
            diag(f"  dest local: OM_LOC|{op.args[0] & LOCAL_INDEX_MASK}")
            diag(f"  skill: tag={op.args[2]>>56}, idx={op.args[2] & LOCAL_INDEX_MASK}")

    # 定位所有 inv_slot
    invs = [(i, op) for i, op in enumerate(target2.ops) if op.opcode == 1541]
    diag(f"inv_slot 调用数: {len(invs)}")
    for i, op in invs[:6]:
        dest_tag = op.args[0] >> OP_NUM_VALUE_BITS
        troop_tag = op.args[1] >> OP_NUM_VALUE_BITS
        diag(f"  ops[{i}]: dest(OM_LOC|{op.args[0] & LOCAL_INDEX_MASK}), troop(tag={troop_tag}, idx={op.args[1] & LOCAL_INDEX_MASK}), slot={op.args[2]}")

    # 定位所有 eq 比较的物品值
    eqs = [(i, op) for i, op in enumerate(target2.ops) if op.opcode == 31]
    for i, op in eqs:
        arg1_tag = op.args[1] >> OP_NUM_VALUE_BITS
        if arg1_tag == TAG_ITEM:
            diag(f"  ops[{i}] eq 比较物品: tag=OM_ITM, index={op.args[1] & LOCAL_INDEX_MASK}")
        elif arg1_tag == TAG_LOCAL_VARIABLE:
            diag(f"  ops[{i}] eq 比较 local: OM_LOC|{op.args[1] & LOCAL_INDEX_MASK}")





def detect_max_local(menu: Menu) -> int:
    max_idx = -1
    for ops in [menu.ops] + [opt.conds + opt.cons for opt in menu.opts]:
        for op in ops:
            for arg in op.args:
                if (arg >> OP_NUM_VALUE_BITS) == TAG_LOCAL_VARIABLE:
                    idx = arg & LOCAL_INDEX_MASK
                    if idx > max_idx:
                        max_idx = idx
    return max_idx


def auto_rollback(menus_path: str, qstr_path: str,
                  bak_menus: str, bak_qstr: str,
                  reason: str) -> None:
    print(f"\n原因: {reason}")
    if os.path.exists(bak_menus):
        shutil.copy2(bak_menus, menus_path)
        print(f"已从 {bak_menus} 恢复 {menus_path}")
    if os.path.exists(bak_qstr):
        shutil.copy2(bak_qstr, qstr_path)
        print(f"已从 {bak_qstr} 恢复 {qstr_path}")

def annotate_csv(csv_path: str, lang: str, item_ids: Tuple[int, ...]) -> None:
    """在 game_menus.csv 末尾追加注入说明（纯注释，不影响游戏）。"""
    if not os.path.exists(csv_path):
        return
    lines = [
        "",
        "# --- 以下由 inject_rare_item_scout.py 注入 ---",
        f"# 追踪物品: {item_ids[0]}, {item_ids[1]}, {item_ids[2]}, {item_ids[3]}",
        f"# 语言: {lang}",
    ]
    with open(csv_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")




def verify_injection(menus_path: str, qstr_path: str,
                     target_menu: Menu, cont_opt: MenuOption,
                     local_base: int,
                     original_used_locals: Optional[Set[int]] = None,
                     dry_run: bool = False,
                     bak_menus: str = "", bak_qstr: str = "") -> List[str]:
    errors: List[str] = []

    rt_errors = verify_roundtrip(menus_path)
    if rt_errors:
        errors.append(f"Roundtrip 不一致: {rt_errors[0]}")

    if not has_injection_signature(target_menu.ops):
        errors.append("注入签名缺失（需要完整的首尾双标记块）")

    opener_count = sum(1 for op in target_menu.ops if op.opcode in (4, 6, 11))
    closer_count = sum(1 for op in target_menu.ops if op.opcode == 3)
    if opener_count != closer_count:
        tb_cnt = sum(1 for op in target_menu.ops if op.opcode == 4)
        fr_cnt = sum(1 for op in target_menu.ops if op.opcode == 6)
        fp_cnt = sum(1 for op in target_menu.ops if op.opcode == 11)
        errors.append(
            f"块配对不匹配: try_begin({tb_cnt})+for_range({fr_cnt})+for_parties({fp_cnt})={opener_count} != try_end({closer_count})")

    _, has_correct, bad_indices = find_display_message_in_cons(cont_opt.cons)
    if not has_correct:
        if bad_indices:
            errors.append(f"display_message 参数错误（发现 {len(bad_indices)} 个错误）")
        else:
            errors.append("continue 选项缺少 display_message")

    if original_used_locals is not None:
        injected_max = local_base + 18
        conflicts = [idx for idx in original_used_locals
                     if local_base <= idx <= injected_max and local_base > 0]
        if conflicts:
            suffix = "（local_base=0 是故意复用，跳过此检测）" if local_base == 0 else ""
            errors.append(
                f"局部变量冲突: 注入范围 {local_base}..{injected_max} "
                f"与已有局部变量索引 {conflicts} 重叠{suffix}"
            )

    if errors and not dry_run and bak_menus:
        auto_rollback(menus_path, qstr_path, bak_menus, bak_qstr, errors[0])

    return errors


# ============================================================
# 9. 主逻辑
# ============================================================


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rare Item Scout Injector - 稀有物品探测注入工具")
    parser.add_argument("menus_file", help="menus.txt 路径")
    parser.add_argument("--item1", type=int, default=469)
    parser.add_argument("--item2", type=int, default=272)
    parser.add_argument("--item3", type=int, default=150)
    parser.add_argument("--item4", type=int, default=101,
                        help="物品4序号（默认值对应战团原版的天鹅绒`itm_velvet`）")
    parser.add_argument("--skl-trade", type=int, default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--restore", action="store_true")
    parser.add_argument("--with-diag", action="store_true",
                        help="注入游戏内诊断标记（[RARE] 消息）")
    parser.add_argument("--lang", type=str, default="en",
                        choices=["en", "zh-CN"],
                        help="语言（en=英语，zh-CN=简体中文）")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--qstr-file", default=None)
    parser.add_argument("--no-verify", action="store_true")
    args = parser.parse_args()

    # ---- 诊断模式：dry-run 时自动启用全部诊断 ----
    global DIAG
    DIAG = args.dry_run
    if DIAG:
        print("  [DIAG] 诊断模式已启用")


    menus_path = args.menus_file
    base_dir = os.path.dirname(menus_path) or "."
    qstr_path = args.qstr_file or os.path.join(base_dir, "quick_strings.txt")
    bak_menus = menus_path + ".bak"
    bak_qstr = qstr_path + ".bak"

    if args.restore:
        if os.path.exists(bak_menus):
            shutil.copy2(bak_menus, menus_path)
            print(f"已从 {bak_menus} 恢复 {menus_path}")
        if os.path.exists(bak_qstr):
            shutil.copy2(bak_qstr, qstr_path)
            print(f"已从 {bak_qstr} 恢复 {qstr_path}")
        return

    if not os.path.exists(menus_path):
        print(f"错误：can't find {menus_path}")
        sys.exit(1)
    if not os.path.exists(qstr_path):
        print(f"错误：can't find {qstr_path}（可用 --qstr-file 指定）")
        sys.exit(1)

    menus = parse_menu_bytes(menus_path)
    print(f"已解析 {len(menus)} 个菜单")

    target = None
    for m in menus:
        if m.raw_id == "menu_town_trade_assessment":
            target = m
            break
    if not target:
        print("错误：can't find menu_town_trade_assessment")
        sys.exit(1)
    print(f"  目标: {target.raw_id}")

    # ---- 查找 begin 菜单 ----
    target_begin = None
    for m in menus:
        if m.raw_id == "menu_town_trade_assessment_begin":
            target_begin = m
            break
    if not target_begin:
        print("错误：can't find menu_town_trade_assessment_begin")
        sys.exit(1)
    print(f"  begin 菜单: {target_begin.raw_id} (ops: {len(target_begin.ops)})")

    skl_val = args.skl_trade
    if skl_val is None:
        skl_val = extract_skl_trade(menus)
        if skl_val is None:
            print("错误：无法自动提取 skl_trade，请用 --skl-trade 指定")
            sys.exit(1)
        print(f"  skl_trade = {skl_val}")

    cont_opt = find_continue_option(target)
    if not cont_opt:
        print("错误：菜单无可用选项")
        sys.exit(1)
    print(f"  选项: {cont_opt.raw_id}")

    # ---- Phase 1 诊断：目标菜单分析 ----
    if DIAG:
        diag(f"--- 目标菜单分析 ---")
        diag(f"菜单 ops 总数: {len(target.ops)}")
        diag(f"菜单 opts 总数: {len(target.opts)}")
        # 统计局部变量使用
        local_usage = {}
        for ops_list in [target.ops] + [o.conds + o.cons for o in target.opts]:
            for op in ops_list:
                for arg in op.args:
                    if (arg >> OP_NUM_VALUE_BITS) == TAG_LOCAL_VARIABLE:
                        idx = arg & LOCAL_INDEX_MASK
                        local_usage[idx] = local_usage.get(idx, 0) + 1
        if local_usage:
            max_used = max(local_usage.keys())
            diag(f"局部变量范围: 0..{max_used} (共 {len(local_usage)} 个被使用)")
            diag(f"最高使用的局部索引: {max_used}")
            # 输出前 10 个最常用的局部变量
            sorted_usage = sorted(local_usage.items(), key=lambda x: -x[1])
            for idx, count in sorted_usage[:10]:
                diag(f"  OM_LOC|{idx}: {count} 次引用")
        diag(f"原始菜单块配对: try_begin={sum(1 for op in target.ops if op.opcode==4)}, try_end={sum(1 for op in target.ops if op.opcode==3)}")


    # ---- 幂等性清除 ----
    print()
    print("----- 旧注入检查 -----")
    ops_before = len(target.ops)
    target.ops, clean_report = clean_old_injection(
        target.ops, force=args.force, dry_run=args.dry_run)
    cleaned_count = ops_before - len(target.ops)

    if clean_report["signature_found"]:
        print(f"  检测到注入签名，已清除 {cleaned_count} 条旧操作")
    elif clean_report["heuristic_found"]:
        if clean_report["cleaned"]:
            print(f"  启发式扫描发现疑似旧注入，已清除 {cleaned_count} 条操作")
        else:
            print(f"  启发式扫描发现疑似旧注入，但未清除")
        print(f"  详情: {clean_report['heuristic_details']}")
    else:
        print(f"  未发现旧注入（{clean_report['heuristic_details']}）")

    # ---- 局部变量基址：复用 0-18（原始 ops 已执行完毕，覆写安全）----
    local_base = LOCAL_BASE
    print(f"  局部变量基址: {local_base}（复用原始菜单的 0-18，原始 ops 已执行完毕）")

    # ---- 检查局部变量上限 ----
    if local_base + 18 >= 64:
        print(f"错误：局部变量需求 ({local_base}..{local_base+18}) 超过 Warband 上限 (64)。")
        sys.exit(1)

    # ---- 注入前快照 ----
    original_used_locals: Set[int] = set()
    for op in target.ops:
        for arg in op.args:
            if (arg >> OP_NUM_VALUE_BITS) == TAG_LOCAL_VARIABLE:
                original_used_locals.add(arg & LOCAL_INDEX_MASK)
    for opt in target.opts:
        for op in opt.conds + opt.cons:
            for arg in op.args:
                if (arg >> OP_NUM_VALUE_BITS) == TAG_LOCAL_VARIABLE:
                    original_used_locals.add(arg & LOCAL_INDEX_MASK)

    # ---- 生成扫描代码 ----
    qstr_mgr = QStrManager(qstr_path)
    print(f"  quick_strings: {len(qstr_mgr.keys)} 条")
    item_vals = [E.I(args.item1), E.I(args.item2), E.I(args.item3), E.I(args.item4)]
    print(f"  物品: {args.item1} / {args.item2} / {args.item3} / {args.item4}")

    new_ops = make_scan_ops(skl_val, item_vals[0], item_vals[1], item_vals[2], item_vals[3],
                            qstr_mgr, local_base=local_base,
                            lang=args.lang, with_diag=args.with_diag)


    # ---- Phase 8: 生成 begin 菜单提示文本 ----
    # 检测是否已注入：检查 begin 菜单 ops 中是否有 party_skill(1685)
    already_has_hint = any(op.opcode == 1685 for op in target_begin.ops)
    begin_hint_ops = [] if already_has_hint else \
        make_begin_hint_ops(skl_val, qstr_mgr,
                            lang=args.lang,
                            with_diag=args.with_diag)
    if begin_hint_ops:
        print(f"  begin 提示: 生成了 {len(begin_hint_ops)} 条操作")
    else:
        print(f"  begin 提示: ops 已注入，跳过")


    # ---- Phase 2 诊断：生成的 ops 结构摘要 ----
    if DIAG:
        print()
        summarize_ops(new_ops, "生成的操作")
        dump_local_alloc(local_base)
        # Phase 4.2：注入签名验证
        diag(f"INJECT_START_SIG: {INJECT_START_SIG:#x} ('{(INJECT_START_SIG).to_bytes(4,"big").decode("ascii",errors="replace")}')")
        diag(f"INJECT_SIG:       {INJECT_SIG:#x} ('{(INJECT_SIG).to_bytes(4,"big").decode("ascii",errors="replace")}')")
        # 检查是否是 dry-run（此时尚未注入到 target.ops）
        if not args.dry_run:
            # 已注入到 target.ops，检查注入后的签名
            sig_ok = has_injection_signature(target.ops)
            diag(f"注入后签名检测: {'✅' if sig_ok else '❌ 缺失'}")


    # ---- 修复 display_message ----
    msg_fixed = fix_display_message(cont_opt)
    if msg_fixed:
        print("  display_message: 已修复（删除错误参数，插入正确版本）")
    else:
        _, has_correct, _ = find_display_message_in_cons(cont_opt.cons)
        if has_correct:
            print("  display_message: 已有正确版本，跳过")

    # ---- 预览模式 ----
    if args.dry_run:
        print()
        print("===== 预览模式 ====")
        print(f"将在 {target.raw_id} 追加 {len(new_ops)} 条操作（含首尾双标记）")
        if begin_hint_ops:
            print(f"将在 {target_begin.raw_id} 追加 {len(begin_hint_ops)} 条操作（display_message 方式）")
        print(f"  旧注入清理: {cleaned_count} 条")
        print(f"  局部变量基址: {local_base}")
        tb_count = sum(1 for op in target.ops if op.opcode == 4)
        te_count = sum(1 for op in target.ops if op.opcode == 3)
        print(f"  try_begin/try_end: {tb_count}/{te_count}")
        if begin_hint_ops:
            bt_count = sum(1 for op in target_begin.ops if op.opcode == 4)
            print(f"  begin 菜单: ops={len(target_begin.ops)} (+{len(begin_hint_ops)}), msg 提示: Recent Messages 显示")


        print()
        print("----- dry-run 静态检查 -----")
        verr = verify_injection(menus_path, qstr_path, target, cont_opt,
                                 local_base,
                                 original_used_locals=original_used_locals,
                                 dry_run=True)
        if verr:
            print("⚠ 发现以下问题（dry-run 模式，未修改文件，无需回滚）：")
            for e in verr:
                print(f"  ✗ {e}")
        else:
            print("  ✓ 所有静态检查通过")
        return

    # ---- 备份 ----
    if not os.path.exists(bak_menus) or args.force:
        shutil.copy2(menus_path, bak_menus)
        print(f"备份 -> {bak_menus}")
    if not os.path.exists(bak_qstr) or args.force:
        shutil.copy2(qstr_path, bak_qstr)
        print(f"备份 -> {bak_qstr}")

    # ---- 注入（含写入保护和回滚）----
    target.ops.extend(new_ops)
    print(f"  已追加 {len(new_ops)} 条操作（含首尾双标记）")


    # ---- Phase 8: 注入 begin 菜单提示 ----
    if begin_hint_ops:
        target_begin.ops.extend(begin_hint_ops)
        print(f"  已追加 {len(begin_hint_ops)} 条操作到 {target_begin.raw_id}")




    try:
        qstr_mgr.save()
        out_path = args.output or menus_path
        serialized = serialize_menu_list(menus)
        write_file(out_path, serialized)
        print(f"\n✓ 已保存到 {out_path}")
    except IOError as e:
        if os.path.exists(bak_menus):
            shutil.copy2(bak_menus, menus_path)
        if os.path.exists(bak_qstr):
            shutil.copy2(bak_qstr, qstr_path)
        print(f"错误：文件写入失败 ({e})，已从备份恢复")
        sys.exit(1)

    # ---- 注入后验证 ----
    if not args.no_verify:
        print()
        print("----- 验证 -----")
        verr = verify_injection(out_path, qstr_path, target, cont_opt,
                                 local_base,
                                 original_used_locals=original_used_locals,
                                 dry_run=False,
                                 bak_menus=bak_menus, bak_qstr=bak_qstr)
        if verr:
            for e in verr:
                print(f"  ✗ {e}")
            sys.exit(1)
        else:
            print("  ✓ Roundtrip 一致性通过")
            print("  ✓ 注入双标记验证通过")
            print("  ✓ 操作码配对正确")
            print("  ✓ display_message 正确")
            print(f"  ✓ 局部变量范围安全 (基址 {local_base})")
            print("  ✓ quick_strings 完整")
            print("\n✓ 验证完成")


    # ---- CSV 注释（纯参考） ----
    csv_path = os.path.join(base_dir, "game_menus.csv")
    annotate_csv(csv_path, args.lang, (args.item1, args.item2, args.item3, args.item4))

    # ---- Phase 5 诊断：注入后文件验证 ----
    post_inject_verify(out_path)



if __name__ == "__main__":
    main()
